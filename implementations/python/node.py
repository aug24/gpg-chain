"""GPG Chain node entrypoint."""
import click
import uvicorn


@click.command()
@click.option("--addr", default="0.0.0.0:8080", help="Listen address (host:port)")
@click.option("--store-dir", default="./data", help="Path to store directory")
@click.option("--store-prefix-len", default=4, help="Directory prefix length (default 4 = 2+2)")
@click.option("--cache-size", default=128, help="LRU block cache size")
@click.option("--peers", default="", help="Comma-separated bootstrap peer URLs")
@click.option("--domains", default="", help="Comma-separated permitted email domains")
@click.option("--allow-all-domains", is_flag=True, help="Accept keys from any domain")
@click.option("--allow-private-peers", is_flag=True, help="Allow peers on private/loopback IPs (for internal/container deployments)")
@click.option("--node-url", default="", help="Public URL of this node (for well-known)")
def main(addr, store_dir, store_prefix_len, cache_size, peers, domains, allow_all_domains, allow_private_peers, node_url):
    """Start a GPG Chain node."""
    from gpgchain.api.app import create_app

    peer_list = [p.strip() for p in peers.split(",") if p.strip()]
    domain_list = [d.strip() for d in domains.split(",") if d.strip()]

    app = create_app(
        store_dir=store_dir,
        store_prefix_len=store_prefix_len,
        cache_size=cache_size,
        peers=peer_list,
        domains=domain_list,
        allow_all_domains=allow_all_domains,
        allow_private_peers=allow_private_peers,
        node_url=node_url,
    )

    host, port = addr.rsplit(":", 1)
    uvicorn.run(app, host=host, port=int(port))


if __name__ == "__main__":
    main()
