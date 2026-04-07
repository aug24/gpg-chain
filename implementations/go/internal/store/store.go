// Package store defines the Store interface and implementations.
package store

import "github.com/aug24/gpg-chain/internal/chain"

// Store is the persistence interface for the ledger.
type Store interface {
	// Add persists a new block. Returns error if fingerprint already exists.
	Add(block *chain.Block) error

	// Get returns the block for the given fingerprint, or nil if not found.
	Get(fingerprint string) (*chain.Block, error)

	// All returns all blocks.
	All() ([]*chain.Block, error)

	// AddSig appends a SigEntry to a block's sig chain.
	AddSig(fingerprint string, entry *chain.SigEntry) error

	// Revoke marks a block as revoked.
	Revoke(fingerprint string, revocationSig string) error

	// Hashes returns {fingerprint: sig_chain_head} for all blocks.
	// Must be fast — implementations should not load full block data.
	Hashes() (map[string]string, error)
}
