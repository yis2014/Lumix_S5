# Public key material and key status

## Recovered lens key material

The following 16-byte ASCII materials were read from the main-core runtime while tracing the lens update key setup API at `0x868C69EC`.

- Physical address `0x08AB4E88`  `WZdHXAXgu7Cn691V`
- Physical address `0x08AB4E98`  `ML/k5tjaCr9zKjRfR`

The two values are adjacent slices of a longer base64-like material region. They were tested against the S5 body `program` known-plaintext oracle across the recorded AES mode and byte-order combinations and did not decrypt the body program partition.

## Metadata verification public key

`S5_V28_V29_metadata_public_0ffaf83e958b.pem` is the recovered S5 V2.8/V2.9 metadata verification public key. It is public verification material. It does not provide the signing private key or the body payload decryption key.

## Body payload key

No body payload AES key has been recovered and validated. `dumps/keyregion.bin` and `dumps/keyregion_big.bin` are raw capture windows retained for independent review. High-entropy bytes in these windows must not be treated as a key without full-resource known-plaintext validation.
