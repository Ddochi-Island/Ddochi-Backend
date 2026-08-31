package server

import (
	"errors"
	"io"
	"mime/multipart"
	"net/http"
)

type multipartFile struct {
	body        io.Reader
	contentType string
	size        int64 // -1 if unknown
	close       func()
}

// openMultipart picks the first file part out of a multipart/form-data
// request body, returning a reader bounded by maxBytes via the caller's
// MaxBytesReader-wrapped Body. A separate "content_type" form field
// overrides the part's Content-Type when present.
//
// Why we don't use ParseMultipartForm: it buffers everything into RAM
// or temp files up to a memory threshold; we want to stream straight
// into the storage backend. The mime/multipart Reader gives us that.
func (h *StorageHandlers) openMultipart(r *http.Request, boundary string) (*multipartFile, error) {
	r.Body = http.MaxBytesReader(nil, r.Body, h.maxUploadBytes)
	mr := multipart.NewReader(r.Body, boundary)
	var explicitCT string
	for {
		part, err := mr.NextPart()
		if err == io.EOF {
			break
		}
		if err != nil {
			return nil, err
		}
		switch part.FormName() {
		case "content_type":
			b, err := io.ReadAll(io.LimitReader(part, 200))
			_ = part.Close()
			if err != nil {
				return nil, err
			}
			explicitCT = string(b)
		case "file":
			ct := explicitCT
			if ct == "" {
				ct = part.Header.Get("Content-Type")
			}
			return &multipartFile{
				body:        part,
				contentType: ct,
				size:        -1,
				close:       func() { _ = part.Close() },
			}, nil
		default:
			_ = part.Close()
		}
	}
	return nil, errors.New("multipart: no 'file' part found")
}
