// In-memory store for tests only.
package store

import (
	"fmt"
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

func (m *MemoryStore) Add(block *chain.Block) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, exists := m.blocks[block.Fingerprint]; exists {
		return fmt.Errorf("block already exists for fingerprint %s", block.Fingerprint)
	}
	copied := *block
	copied.SigEntries = append([]*chain.SigEntry{}, block.SigEntries...)
	m.blocks[block.Fingerprint] = &copied
	return nil
}

func (m *MemoryStore) Get(fp string) (*chain.Block, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	b, ok := m.blocks[fp]
	if !ok {
		return nil, nil
	}
	copied := *b
	copied.SigEntries = append([]*chain.SigEntry{}, b.SigEntries...)
	return &copied, nil
}

func (m *MemoryStore) All() ([]*chain.Block, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	result := make([]*chain.Block, 0, len(m.blocks))
	for _, b := range m.blocks {
		copied := *b
		copied.SigEntries = append([]*chain.SigEntry{}, b.SigEntries...)
		result = append(result, &copied)
	}
	return result, nil
}

func (m *MemoryStore) AddSig(fp string, entry *chain.SigEntry) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	b, ok := m.blocks[fp]
	if !ok {
		return fmt.Errorf("block not found: %s", fp)
	}
	b.SigEntries = append(b.SigEntries, entry)
	b.SigChainHead = entry.Hash
	return nil
}

func (m *MemoryStore) Revoke(fp, sig string) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	b, ok := m.blocks[fp]
	if !ok {
		return fmt.Errorf("block not found: %s", fp)
	}
	b.Revoked = true
	b.RevocationSig = sig
	return nil
}

func (m *MemoryStore) Hashes() (map[string]string, error) {
	m.mu.RLock()
	defer m.mu.RUnlock()
	result := make(map[string]string, len(m.blocks))
	for fp, b := range m.blocks {
		result[fp] = b.SigChainHead
	}
	return result, nil
}
