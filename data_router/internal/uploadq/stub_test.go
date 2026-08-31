package uploadq

import "github.com/redesign2/services/data_router/internal/storage"

// stubMeta returns a minimal completed result for tests that need to
// drive jobs to terminal states without invoking a real backend.
func stubMeta(id string) storage.ObjectMeta {
	return storage.ObjectMeta{ID: id, Backend: "test", Key: id, Size: 1}
}
