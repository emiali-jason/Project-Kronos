# WO06H R5 relation binding fixtures

Status: OFFLINE ENGINEERING ONLY. These exact-byte copies are test inputs;
their presence in the repository does not enroll a compatibility relation or
authorize recovery, acceptance restoration, a runtime transition or production
operations. The recorded PID and revision in the target fixture are historical
metadata used for offline capability-map validation, not proof of a loaded
successor runtime.

The reviewed relation and retained source epoch were copied from the independent
preimplementation proof for WO06H-R5-CANONICAL-RELATION-BINDING-CORRECTION on
10 October 2026. The target fixture was copied from the final R5 engineering
capability proof. The copies preserve their original bytes. No credentials,
tokens or unrelated production records are included.

| Fixture | Bytes | SHA-256 |
| --- | ---: | --- |
| FINAL-DIRECT-SUCCESSOR-RELATION.json | 10,035 | e5d63954815ffa526390e1d5d0e668a8c490371ead305c85a14b43d6c300c58e |
| RETAINED-SOURCE-EPOCH.json | 2,304 | 68f11b05428fafd16c97479154e1b015991bef8b7d21c78c373bb61c2933ad37 |
| FINAL-TARGET-CAPABILITY.json | 3,337 | 81fb09d0babb1900a7f3d5a96d0ed17233003062a48484564da3286c89d4e97f |

Canonical serialization of the reviewed relation is 8,299 bytes with SHA-256
707ca654076df91af1935d082a569d8d8c0335f52a08d63a8047ea1a94e4e48b.
This is a distinct physical artifact from the 10,035-byte review artifact.
The test verifies recursive typed equality of the parsed contents, the unchanged
default-approved validator, and retention/readback in disposable stores only.

The bound relation identity is
WO06H-SUCCESSOR_COMPATIBILITY-4f6aac6c3a9f59fe2e19b788fb6266fec1a239358e71f2abc9f9c9ac4c0731ef;
its existing internal integrity remains
500d75b4b1093b776886bab486a55ba4c2c9e1824b75564a9cfb0ecaba7b3e03.
Physical encoding equivalence does not replace semantic approval or relax the
existing reader's canonical-encoding requirement.
