// Package gpg handles key parsing, payload construction, and signature verification.
package gpg

import (
	"bytes"
	"crypto/sha256"
	"encoding/base64"
	"fmt"
	"regexp"
	"strings"

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

// VerifyDetachedSig verifies a base64-encoded detached binary GPG signature over payload.
// Returns true if the signature is valid for the given armored public key.
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
	_, err = pgpcrypto.CheckDetachedSignature(
		keyring,
		bytes.NewReader(payload),
		bytes.NewReader(sigBytes),
		nil,
	)
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
