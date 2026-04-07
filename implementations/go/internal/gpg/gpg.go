// Package gpg handles key parsing, payload construction, and signature verification.
package gpg

// ParseArmoredKey parses an ASCII-armored public key.
// Returns (fingerprint, uids) where fingerprint is uppercase hex, no spaces.
func ParseArmoredKey(armored string) (fingerprint string, uids []string, err error) {
	panic("not implemented")
}

// CheckKeyStrength returns an error if the key does not meet minimum strength.
// Rules: RSA >= 2048 bits; DSA-1024 rejected; Ed25519 accepted.
func CheckKeyStrength(armored string) error {
	panic("not implemented")
}

// ExtractEmailDomains returns lowercase email domains from UID strings.
func ExtractEmailDomains(uids []string) []string {
	panic("not implemented")
}

// SubmitPayload returns the GPGCHAIN_SUBMIT_V1 binary payload.
func SubmitPayload(fingerprint, armoredKey string, timestamp int64) []byte {
	panic("not implemented")
}

// TrustPayload returns the GPGCHAIN_TRUST_V1 binary payload.
func TrustPayload(blockHash, signerFingerprint string, timestamp int64) []byte {
	panic("not implemented")
}

// RevokePayload returns the GPGCHAIN_REVOKE_V1 binary payload.
func RevokePayload(fingerprint, blockHash string) []byte {
	panic("not implemented")
}

// VerifyDetachedSig verifies a base64-encoded detached GPG signature over payload.
// Returns true if valid.
func VerifyDetachedSig(payload []byte, b64Sig, armoredPublicKey string) bool {
	panic("not implemented")
}
