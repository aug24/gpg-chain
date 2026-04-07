// Package api defines the HTTP router and all route handlers.
package api

import (
	"encoding/json"
	"net/http"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

func notImplemented(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusNotImplemented)
	json.NewEncoder(w).Encode(map[string]string{"error": "not implemented"})
}

// NewRouter builds and returns the chi router with all routes registered.
func NewRouter() http.Handler {
	r := chi.NewRouter()
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)

	// Public endpoints
	r.Get("/blocks", notImplemented)
	r.Get("/block/{fingerprint}", notImplemented)
	r.Post("/block", notImplemented)
	r.Post("/block/{fingerprint}/sign", notImplemented)
	r.Post("/block/{fingerprint}/revoke", notImplemented)
	r.Get("/search", notImplemented)
	r.Get("/.well-known/gpgchain.json", notImplemented)

	// Peer endpoints
	r.Get("/peers", notImplemented)
	r.Post("/peers", notImplemented)
	r.Get("/p2p/hashes", notImplemented)
	r.Get("/p2p/block/{hash}", notImplemented)
	r.Post("/p2p/block", notImplemented)
	r.Post("/p2p/sign", notImplemented)
	r.Post("/p2p/revoke", notImplemented)

	return r
}
