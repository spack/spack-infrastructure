import click

from spack_secrets.update import update


@click.group()
def cli():
    pass


# Add sub commands
cli.add_command(update)


if __name__ == "__main__":
    cli()
