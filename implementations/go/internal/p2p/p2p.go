// Package p2p handles peer management, gossip, and sync.
package p2p

import "github.com/aug24/gpg-chain/internal/chain"

// PeerList manages the set of known peer URLs.
type PeerList struct {
	peers   []string
	maxSize int
}

func NewPeerList(maxSize int) *PeerList {
	return &PeerList{maxSize: maxSize}
}

func (p *PeerList) Add(url string) error { panic("not implemented") }
func (p *PeerList) All() []string        { return append([]string{}, p.peers...) }

// Gossip fans out events to K randomly selected peers.
type Gossip struct {
	peers   *PeerList
	fanout  int
	seen    map[string]struct{}
}

func NewGossip(peers *PeerList, fanout int) *Gossip {
	return &Gossip{peers: peers, fanout: fanout, seen: make(map[string]struct{})}
}

func (g *Gossip) GossipBlock(block *chain.Block, origin string)                     { panic("not implemented") }
func (g *Gossip) GossipSig(fp string, entry *chain.SigEntry, origin string)         { panic("not implemented") }
func (g *Gossip) GossipRevoke(fp string, revocationSig string, origin string)       { panic("not implemented") }

// Sync handles connect-time sync and periodic cross-validation.
type Sync struct{}

func (s *Sync) SyncWithPeer(peerURL string) error           { panic("not implemented") }
func (s *Sync) CrossValidate() ([]string, error)            { panic("not implemented") }
