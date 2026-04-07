// GPG Chain CLI client binary.
package main

import (
	"flag"
	"fmt"
	"os"
)

var server = flag.String("server", "http://localhost:8080", "node URL ($GPGCHAIN_SERVER)")
var keyid = flag.String("keyid", "", "own key fingerprint ($GPGCHAIN_KEYID)")

func main() {
	if s := os.Getenv("GPGCHAIN_SERVER"); s != "" {
		*server = s
	}
	if k := os.Getenv("GPGCHAIN_KEYID"); k != "" {
		*keyid = k
	}

	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: gpgchain <command> [flags]")
		fmt.Fprintln(os.Stderr, "commands: add, sign, revoke, list, check, show, search, verify")
		os.Exit(1)
	}

	switch os.Args[1] {
	case "add":
		cmdAdd()
	case "sign":
		cmdSign()
	case "revoke":
		cmdRevoke()
	case "list":
		cmdList()
	case "check":
		cmdCheck()
	case "show":
		cmdShow()
	case "search":
		cmdSearch()
	case "verify":
		cmdVerify()
	default:
		fmt.Fprintf(os.Stderr, "unknown command: %s\n", os.Args[1])
		os.Exit(1)
	}
}

func cmdAdd()    { panic("not implemented") }
func cmdSign()   { panic("not implemented") }
func cmdRevoke() { panic("not implemented") }
func cmdList()   { panic("not implemented") }
func cmdCheck()  { panic("not implemented") }
func cmdShow()   { panic("not implemented") }
func cmdSearch() { panic("not implemented") }
func cmdVerify() { panic("not implemented") }
