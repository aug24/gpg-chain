// SQLite-backed store using modernc.org/sqlite (pure Go, no CGo).
package store

import (
	"database/sql"
	"encoding/json"
	"fmt"

	_ "modernc.org/sqlite"

	"github.com/aug24/gpg-chain/internal/chain"
)

const schema = `
CREATE TABLE IF NOT EXISTS blocks (
	fingerprint      TEXT PRIMARY KEY,
	hash             TEXT NOT NULL UNIQUE,
	armored_key      TEXT NOT NULL,
	uids             TEXT NOT NULL,
	submit_timestamp INTEGER NOT NULL,
	self_sig         TEXT NOT NULL,
	sig_chain_head   TEXT NOT NULL DEFAULT '',
	revoked          INTEGER NOT NULL DEFAULT 0,
	revocation_sig   TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sig_entries (
	hash               TEXT PRIMARY KEY,
	block_fingerprint  TEXT NOT NULL REFERENCES blocks(fingerprint),
	prev_hash          TEXT NOT NULL,
	signer_fingerprint TEXT NOT NULL,
	sig                TEXT NOT NULL,
	timestamp          INTEGER NOT NULL,
	signer_armored_key TEXT NOT NULL DEFAULT '',
	source_node        TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS sig_entries_block ON sig_entries(block_fingerprint);
`

// SQLiteStore is the production backing store.
type SQLiteStore struct {
	db *sql.DB
}

// Open opens (or creates) a SQLite database at the given path and runs migrations.
func Open(path string) (*SQLiteStore, error) {
	db, err := sql.Open("sqlite", path)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}
	db.SetMaxOpenConns(1) // SQLite only supports one writer at a time
	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("migrate: %w", err)
	}
	return &SQLiteStore{db: db}, nil
}

func (s *SQLiteStore) Add(block *chain.Block) error {
	uids, err := json.Marshal(block.UIDs)
	if err != nil {
		return fmt.Errorf("marshal uids: %w", err)
	}
	_, err = s.db.Exec(`
		INSERT INTO blocks
		  (fingerprint, hash, armored_key, uids, submit_timestamp, self_sig)
		VALUES (?, ?, ?, ?, ?, ?)`,
		block.Fingerprint, block.Hash, block.ArmoredKey,
		string(uids), block.SubmitTimestamp, block.SelfSig,
	)
	if err != nil {
		return fmt.Errorf("insert block: %w", err)
	}
	return nil
}

func (s *SQLiteStore) Get(fingerprint string) (*chain.Block, error) {
	row := s.db.QueryRow(`
		SELECT hash, armored_key, uids, submit_timestamp, self_sig,
		       sig_chain_head, revoked, revocation_sig
		FROM blocks WHERE fingerprint = ?`, fingerprint)

	block := &chain.Block{Fingerprint: fingerprint}
	var uidsJSON string
	var revoked int
	err := row.Scan(
		&block.Hash, &block.ArmoredKey, &uidsJSON, &block.SubmitTimestamp,
		&block.SelfSig, &block.SigChainHead, &revoked, &block.RevocationSig,
	)
	if err == sql.ErrNoRows {
		return nil, nil
	}
	if err != nil {
		return nil, fmt.Errorf("scan block: %w", err)
	}
	block.Revoked = revoked != 0
	if err := json.Unmarshal([]byte(uidsJSON), &block.UIDs); err != nil {
		return nil, fmt.Errorf("unmarshal uids: %w", err)
	}
	entries, err := s.getSigEntries(fingerprint)
	if err != nil {
		return nil, err
	}
	block.SigEntries = entries
	return block, nil
}

func (s *SQLiteStore) getSigEntries(fingerprint string) ([]*chain.SigEntry, error) {
	rows, err := s.db.Query(`
		SELECT hash, prev_hash, signer_fingerprint, sig, timestamp,
		       signer_armored_key, source_node
		FROM sig_entries WHERE block_fingerprint = ?`, fingerprint)
	if err != nil {
		return nil, fmt.Errorf("query sig entries: %w", err)
	}
	defer rows.Close()

	byHash := make(map[string]*chain.SigEntry)
	for rows.Next() {
		e := &chain.SigEntry{}
		if err := rows.Scan(&e.Hash, &e.PrevHash, &e.SignerFingerprint,
			&e.Sig, &e.Timestamp, &e.SignerArmoredKey, &e.SourceNode); err != nil {
			return nil, fmt.Errorf("scan sig entry: %w", err)
		}
		byHash[e.Hash] = e
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate sig entries: %w", err)
	}
	if len(byHash) == 0 {
		return nil, nil
	}

	// Find the head: the entry whose hash is not referenced as any entry's PrevHash
	referenced := make(map[string]bool)
	for _, e := range byHash {
		referenced[e.PrevHash] = true
	}
	var head *chain.SigEntry
	for _, e := range byHash {
		if !referenced[e.Hash] {
			head = e
			break
		}
	}
	if head == nil {
		return nil, nil
	}

	// Walk backwards from head, then reverse to get oldest→newest
	ordered := make([]*chain.SigEntry, 0, len(byHash))
	cur := head
	for cur != nil {
		ordered = append(ordered, cur)
		cur = byHash[cur.PrevHash]
	}
	for i, j := 0, len(ordered)-1; i < j; i, j = i+1, j-1 {
		ordered[i], ordered[j] = ordered[j], ordered[i]
	}
	return ordered, nil
}

func (s *SQLiteStore) All() ([]*chain.Block, error) {
	rows, err := s.db.Query(`
		SELECT fingerprint, hash, armored_key, uids, submit_timestamp, self_sig,
		       sig_chain_head, revoked, revocation_sig
		FROM blocks`)
	if err != nil {
		return nil, fmt.Errorf("query blocks: %w", err)
	}
	defer rows.Close()

	var blocks []*chain.Block
	for rows.Next() {
		b := &chain.Block{}
		var uidsJSON string
		var revoked int
		if err := rows.Scan(&b.Fingerprint, &b.Hash, &b.ArmoredKey, &uidsJSON,
			&b.SubmitTimestamp, &b.SelfSig, &b.SigChainHead, &revoked, &b.RevocationSig); err != nil {
			return nil, fmt.Errorf("scan block: %w", err)
		}
		b.Revoked = revoked != 0
		if err := json.Unmarshal([]byte(uidsJSON), &b.UIDs); err != nil {
			return nil, fmt.Errorf("unmarshal uids: %w", err)
		}
		blocks = append(blocks, b)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate blocks: %w", err)
	}

	for _, b := range blocks {
		entries, err := s.getSigEntries(b.Fingerprint)
		if err != nil {
			return nil, err
		}
		b.SigEntries = entries
	}
	return blocks, nil
}

func (s *SQLiteStore) AddSig(fingerprint string, entry *chain.SigEntry) error {
	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback() //nolint:errcheck

	_, err = tx.Exec(`
		INSERT INTO sig_entries
		  (hash, block_fingerprint, prev_hash, signer_fingerprint, sig, timestamp,
		   signer_armored_key, source_node)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		entry.Hash, fingerprint, entry.PrevHash, entry.SignerFingerprint,
		entry.Sig, entry.Timestamp, entry.SignerArmoredKey, entry.SourceNode,
	)
	if err != nil {
		return fmt.Errorf("insert sig entry: %w", err)
	}

	_, err = tx.Exec(`UPDATE blocks SET sig_chain_head = ? WHERE fingerprint = ?`,
		entry.Hash, fingerprint)
	if err != nil {
		return fmt.Errorf("update sig_chain_head: %w", err)
	}

	return tx.Commit()
}

func (s *SQLiteStore) Revoke(fingerprint string, revocationSig string) error {
	_, err := s.db.Exec(`
		UPDATE blocks SET revoked = 1, revocation_sig = ? WHERE fingerprint = ?`,
		revocationSig, fingerprint,
	)
	if err != nil {
		return fmt.Errorf("revoke block: %w", err)
	}
	return nil
}

func (s *SQLiteStore) Hashes() (map[string]string, error) {
	rows, err := s.db.Query(`SELECT fingerprint, sig_chain_head FROM blocks`)
	if err != nil {
		return nil, fmt.Errorf("query hashes: %w", err)
	}
	defer rows.Close()

	result := make(map[string]string)
	for rows.Next() {
		var fp, head string
		if err := rows.Scan(&fp, &head); err != nil {
			return nil, fmt.Errorf("scan hash row: %w", err)
		}
		result[fp] = head
	}
	return result, rows.Err()
}
