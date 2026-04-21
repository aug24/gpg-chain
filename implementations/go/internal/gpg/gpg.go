// Package gpg handles key parsing, payload construction, and signature verification.
package gpg

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"log"
	"regexp"
	"strings"
	"time"

	pgpcrypto "github.com/ProtonMail/go-crypto/openpgp"
	"github.com/ProtonMail/go-crypto/openpgp/armor"
	"github.com/ProtonMail/go-crypto/openpgp/packet"
)

// ParseArmoredKey parses an ASCII-armored public key.
// Returns fingerprint (uppercase hex, no spaces) and UIDs.
func ParseArmoredKey(armored string) (fingerprint string, uids []string, err error) {
	el, err := readEntity(armored)
	if err != nil {
		return "", nil, fmt.Errorf("parse armored key: %w", err)
	}
	fingerprint = strings.ToUpper(fmt.Sprintf("%x", el.PrimaryKey.Fingerprint))
	for name := range el.Identities {
		uids = append(uids, name)
	}
	return fingerprint, uids, nil
}

// CheckKeyStrength returns an error if the key does not meet minimum strength requirements.
// Rules: RSA >= 2048 bits; DSA with p <= 1024 bits rejected; Ed25519 accepted.
func CheckKeyStrength(armored string) error {
	el, err := readEntity(armored)
	if err != nil {
		return fmt.Errorf("parse key: %w", err)
	}
	pk := el.PrimaryKey
	algo := pk.PubKeyAlgo
	switch algo {
	case packet.PubKeyAlgoRSA, packet.PubKeyAlgoRSASignOnly, packet.PubKeyAlgoRSAEncryptOnly:
		bits, err := pk.BitLength()
		if err != nil {
			return fmt.Errorf("get RSA bit length: %w", err)
		}
		if bits < 2048 {
			return fmt.Errorf("RSA key too weak: %d bits (minimum 2048)", bits)
		}
	case packet.PubKeyAlgoDSA:
		bits, err := pk.BitLength()
		if err != nil {
			return fmt.Errorf("get DSA bit length: %w", err)
		}
		if bits <= 1024 {
			return fmt.Errorf("DSA key too weak: %d bits (DSA-1024 rejected)", bits)
		}
	// Ed25519 (EdDSA), ECDSA, ECDH are accepted without a bit length check.
	}
	return nil
}

// ExtractEmailDomains returns lowercase email domains found in UID strings.
func ExtractEmailDomains(uids []string) []string {
	bracketed := regexp.MustCompile(`<[^>]+@([^>]+)>`)
	bare := regexp.MustCompile(`^[^@\s]+@([^@\s]+)$`)
	seen := map[string]struct{}{}
	var domains []string
	for _, uid := range uids {
		var domain string
		if m := bracketed.FindStringSubmatch(uid); m != nil {
			domain = strings.ToLower(m[1])
		} else if m := bare.FindStringSubmatch(strings.TrimSpace(uid)); m != nil {
			domain = strings.ToLower(m[1])
		}
		if domain != "" {
			if _, ok := seen[domain]; !ok {
				seen[domain] = struct{}{}
				domains = append(domains, domain)
			}
		}
	}
	return domains
}

// SubmitPayload constructs the GPGCHAIN_SUBMIT_V1 binary payload.
//
//	GPGCHAIN_SUBMIT_V1 \x00 <fingerprint> \x00 <sha256_of_armored_key> \x00 <timestamp>
func SubmitPayload(fingerprint, armoredKey string, timestamp int64) []byte {
	keyHash := sha256.Sum256([]byte(armoredKey))
	keyHashHex := strings.ToUpper(fmt.Sprintf("%x", keyHash))
	return joinNull("GPGCHAIN_SUBMIT_V1", fingerprint, keyHashHex, fmt.Sprintf("%d", timestamp))
}

// TrustPayload constructs the GPGCHAIN_TRUST_V1 binary payload.
//
//	GPGCHAIN_TRUST_V1 \x00 <block_hash> \x00 <signer_fingerprint> \x00 <timestamp>
func TrustPayload(blockHash, signerFingerprint string, timestamp int64) []byte {
	return joinNull("GPGCHAIN_TRUST_V1", blockHash, signerFingerprint, fmt.Sprintf("%d", timestamp))
}

// RevokePayload constructs the GPGCHAIN_REVOKE_V1 binary payload.
//
//	GPGCHAIN_REVOKE_V1 \x00 <fingerprint> \x00 <block_hash>
func RevokePayload(fingerprint, blockHash string) []byte {
	return joinNull("GPGCHAIN_REVOKE_V1", fingerprint, blockHash)
}

// Sign creates a base64-encoded detached binary GPG signature over payload.
// armoredPrivateKey must include the private key material.
func Sign(payload []byte, armoredPrivateKey string) (string, error) {
	block, err := armor.Decode(strings.NewReader(armoredPrivateKey))
	if err != nil {
		return "", fmt.Errorf("decode private key armor: %w", err)
	}
	el, err := pgpcrypto.ReadEntity(packet.NewReader(block.Body))
	if err != nil {
		return "", fmt.Errorf("read private key: %w", err)
	}
	var buf bytes.Buffer
	if err := pgpcrypto.DetachSign(&buf, el, bytes.NewReader(payload), nil); err != nil {
		return "", fmt.Errorf("detach sign: %w", err)
	}
	return base64.StdEncoding.EncodeToString(buf.Bytes()), nil
}

// VerifyDetachedSig verifies a base64-encoded detached binary GPG signature over payload.
// Returns true if the signature is valid for the given armored public key.
//
// We allow a 60-second clock skew tolerance so that signatures created at nearly
// the same instant as verification don't fail due to sub-second timing differences
// between the signing client and this node. go-crypto treats a signature whose
// CreationTime is strictly after config.Now() as "expired", so we advance the
// reference clock slightly to absorb any skew.
func VerifyDetachedSig(payload []byte, b64Sig, armoredPublicKey string) bool {
	sigBytes, err := base64.StdEncoding.DecodeString(b64Sig)
	if err != nil {
		return false
	}
	el, err := readEntity(armoredPublicKey)
	if err != nil {
		return false
	}
	keyring := pgpcrypto.EntityList{el}
	cfg := &packet.Config{
		Time: func() time.Time {
			// Add 60s tolerance so signatures created "just now" by a remote
			// client are not rejected as being from the future.
			return time.Now().Add(60 * time.Second)
		},
	}
	_, err = pgpcrypto.CheckDetachedSignature(
		keyring,
		bytes.NewReader(payload),
		bytes.NewReader(sigBytes),
		cfg,
	)
	if err != nil {
		log.Printf("DEBUG VerifyDetachedSig: FAILED error=%v payloadLen=%d sigLen=%d", err, len(payload), len(sigBytes))
	}
	return err == nil
}

// --- helpers ---

func readEntity(armored string) (*pgpcrypto.Entity, error) {
	block, err := armor.Decode(strings.NewReader(armored))
	if err != nil {
		return nil, fmt.Errorf("decode armor: %w", err)
	}
	el, err := pgpcrypto.ReadEntity(packet.NewReader(block.Body))
	if err != nil {
		return nil, fmt.Errorf("read entity: %w", err)
	}
	return el, nil
}

var null = []byte{0x00}

func joinNull(parts ...string) []byte {
	var buf []byte
	for i, p := range parts {
		if i > 0 {
			buf = append(buf, null...)
		}
		buf = append(buf, []byte(p)...)
	}
	return buf
}
