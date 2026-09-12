# Node Registry (v0.7)

`nodes.NodeRegistry`: register/update/get/list/search, `mark_online` /
`mark_offline`, heartbeat, stale cleanup, capability/model/device-class
queries. Repeated refresh never duplicates (ID-keyed replace). Offline nodes
retain metadata, trust status, and benchmark history; the router excludes
them from new tasks. Local node: `node_from_device_profile()` +
`set_local_node()`.
