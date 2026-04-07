// SQLite-backed store using modernc.org/sqlite (pure Go, no CGo).
package store

import (
	"database/sql"
	"fmt"

	_ "modernc.org/sqlite"

	"github.com/aug24/gpg-chain/internal/chain"
)

const schema = `
CREATE TABLE IF NOT EXISTS blocks (
	fingerprint      TEXT PRIMARY KEY,
	hash             TEXT NOT NULL UNIQUE,
	armored_key      TEXT NOT NULL,
	uids             TEXT NOT NULL,  -- JSON array
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
	if _, err := db.Exec(schema); err != nil {
		return nil, fmt.Errorf("migrate: %w", err)
	}
	return &SQLiteStore{db: db}, nil
}

func (s *SQLiteStore) Add(block *chain.Block) error {
	panic("not implemented")
}

func (s *SQLiteStore) Get(fingerprint string) (*chain.Block, error) {
	panic("not implemented")
}

func (s *SQLiteStore) All() ([]*chain.Block, error) {
	panic("not implemented")
}

func (s *SQLiteStore) AddSig(fingerprint string, entry *chain.SigEntry) error {
	panic("not implemented")
}

func (s *SQLiteStore) Revoke(fingerprint string, revocationSig string) error {
	panic("not implemented")
}

func (s *SQLiteStore) Hashes() (map[string]string, error) {
	panic("not implemented")
}
