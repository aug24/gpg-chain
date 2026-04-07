"""GPG Chain CLI client entrypoint."""
import click


@click.group()
@click.option("--server", default="http://localhost:8080", envvar="GPGCHAIN_SERVER")
@click.pass_context
def main(ctx, server):
    """GPG Chain client."""
    ctx.ensure_object(dict)
    ctx.obj["server"] = server


@main.command()
@click.option("--key", required=True, type=click.Path(exists=True))
@click.option("--keyid", required=True, envvar="GPGCHAIN_KEYID")
@click.pass_context
def add(ctx, key, keyid):
    """Add a public key to the ledger."""
    raise NotImplementedError


@main.command()
@click.option("--fingerprint", required=True)
@click.option("--keyid", required=True, envvar="GPGCHAIN_KEYID")
@click.pass_context
def sign(ctx, fingerprint, keyid):
    """Sign a key on the ledger."""
    raise NotImplementedError


@main.command()
@click.option("--fingerprint", required=True)
@click.option("--keyid", required=True, envvar="GPGCHAIN_KEYID")
@click.pass_context
def revoke(ctx, fingerprint, keyid):
    """Revoke your key on the ledger."""
    raise NotImplementedError


@main.command("list")
@click.option("--keyid", required=True, envvar="GPGCHAIN_KEYID")
@click.option("--min-trust", default=0, type=int)
@click.option("--depth", default=2, type=int)
@click.pass_context
def list_keys(ctx, keyid, min_trust, depth):
    """List keys on the ledger."""
    raise NotImplementedError


@main.command()
@click.option("--fingerprint", required=True)
@click.option("--keyid", required=True, envvar="GPGCHAIN_KEYID")
@click.option("--depth", default=2, type=int)
@click.option("--threshold", default=1, type=int)
@click.pass_context
def check(ctx, fingerprint, keyid, depth, threshold):
    """Check trust score for a key."""
    raise NotImplementedError


@main.command()
@click.option("--fingerprint", required=True)
@click.pass_context
def show(ctx, fingerprint):
    """Show full block detail for a key."""
    raise NotImplementedError


@main.command()
@click.option("--query", required=True)
@click.pass_context
def search(ctx, query):
    """Search keys by UID or email."""
    raise NotImplementedError


@main.command()
@click.pass_context
def verify(ctx):
    """Verify all blocks and signature chains on the ledger."""
    raise NotImplementedError


if __name__ == "__main__":
    main()
