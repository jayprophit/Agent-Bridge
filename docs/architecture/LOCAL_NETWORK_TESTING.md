# Local Network Testing (v0.7)

Because only one physical PC is available, cross-device behavior is verified
with two separate OS processes on loopback:

- `tests/node_test_server.py`: real `NodeServerState` over real HTTP on
  `127.0.0.1` ephemeral ports (synthetic fixtures only, never MAT/Genesis).
- `tests/test_node_transport.py::TwoProcessNetworkTests`: pairing, delegation,
  cancel, emergency-stop, replay/privacy/revocation rejections, heartbeat,
  capability refresh — all over real sockets.

This yields REAL_NETWORK_LOCALHOST_VERIFIED. True multi-device validation
(REAL_CROSS_DEVICE_VERIFIED) remains DEVICE_REQUIRED.
