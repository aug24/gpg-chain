// In-memory store for tests only.
package store

import (
	"sync"

	"github.com/aug24/gpg-chain/internal/chain"
)

type MemoryStore struct {
	mu     sync.RWMutex
	blocks map[string]*chain.Block
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{blocks: make(map[string]*chain.Block)}
}

func (m *MemoryStore) Add(block *chain.Block) error        { panic("not implemented") }
func (m *MemoryStore) Get(fp string) (*chain.Block, error) { panic("not implemented") }
func (m *MemoryStore) All() ([]*chain.Block, error)        { panic("not implemented") }
func (m *MemoryStore) AddSig(fp string, e *chain.SigEntry) error { panic("not implemented") }
func (m *MemoryStore) Revoke(fp, sig string) error         { panic("not implemented") }
func (m *MemoryStore) Hashes() (map[string]string, error)  { panic("not implemented") }
