"""Console script for PythX.

This script aims to be an example of how PythX can be used as a developer-friendly
library around the MythX smart contract security analysis API.
"""
import json
import os
import sys
import time
from copy import copy
from os import path

import click
from tabulate import tabulate

from pythx.api import Client
from pythx.cli import opts, utils
from pythx.cli.logger import LOGGER
from pythx.cli.truffle import find_artifacts


@click.group()
def cli():
    """The basic click CLI command group to register our subcommands under."""
    pass  # pragma: no cover


@cli.command(help="Login to your MythX account")
@opts.staging_opt
@opts.config_opt
def login(staging, config):
    """Perform a login action on the API

    :param staging: Boolean whether to use the MythX staging deployment
    :param config: The configuration file's path
    """
    c = utils.recover_client(config_path=config, staging=staging)
    login_resp = c.login()
    LOGGER.debug(
        "Access token %s\nRefresh token: %s",
        login_resp.access_token,
        login_resp.refresh_token,
    )
    click.echo("Successfully logged in as {}".format(c.eth_address))
    utils.update_config(config_path=config, client=c)


@cli.command(help="Log out of your MythX account")
@opts.config_opt
@opts.staging_opt
def logout(config, staging):
    """Perform a logout action on the API.

    :param config: The configuration file's path
    :param staging: Boolean whether to use the MythX staging deployment
    """
    c = utils.recover_client(config_path=config, staging=staging, exit_on_missing=True)
    if c is None:
        click.echo("You are already logged out.")
        sys.exit(0)
    # delete the credentials storage and logout
    os.remove(config)
    c.logout()
    click.echo("Successfully logged out")


@cli.command(help="Refresh your MythX API token")
@opts.staging_opt
@opts.config_opt
def refresh(staging, config):
    """Perform a refresh action on the API.

    :param staging: Boolean whether to use the MythX staging deployment
    :param config: The configuration file's path
    """
    c = utils.recover_client(config_path=config, staging=staging)
    login_resp = c.refresh()
    LOGGER.debug(
        "Access token %s\nRefresh token: %s",
        login_resp.access_token,
        login_resp.refresh_token,
    )
    click.echo("Successfully refreshed tokens for {}".format(c.eth_address))
    utils.update_config(config_path=config, client=c)


@cli.command(help="Get the OpenAPI spec in HTML or YAML format")
@opts.staging_opt
@opts.html_opt
@opts.yaml_opt
def openapi(staging, mode):
    """Return the API's OpenAPI spec data in HTML or YAML format.

    :param staging: Boolean whether to use the MythX staging deployment
    :param mode: The format to return the OpenAPI spec in (HTML or YAML)
    """
    c = Client(staging=staging)  # no auth required
    click.echo(c.openapi(mode).data)


@cli.command(help="Print version information of PythX and the API")
@opts.staging_opt
def version(staging):
    """Return the API's version information as a pretty table.

    :param staging: Boolean whether to use the MythX staging deployment
    """
    c = Client(staging=staging)  # no auth required
    resp = c.version().to_dict()
    data = ((k.title(), v) for k, v in resp.items())
    click.echo(tabulate(data, tablefmt="fancy_grid"))


@cli.command(help="Get the status of an analysis by its UUID")
@opts.config_opt
@opts.staging_opt
@opts.uuid_arg
def status(config, staging, uuid):
    """Return the status of an analysis job as a pretty table.

    :param config: The configuration file's path
    :param staging: Boolean whether to use the MythX staging deployment
    :param uuid: The analysis job's UUID
    """
    c = utils.recover_client(config_path=config, staging=staging)
    resp = c.status(uuid).analysis.to_dict()
    data = ((k, v) for k, v in resp.items())
    click.echo(tabulate(data, tablefmt="fancy_grid"))
    utils.update_config(config_path=config, client=c)


@cli.command(help="Get a greppable overview of submitted analyses")
@opts.config_opt
@opts.staging_opt
@opts.number_opt
def ps(config, staging, number):
    """Return a list of the most recent analyses as a pretty table and exit.

    :param config: The configuration file's path
    :param staging: Boolean whether to use the MythX staging deployment
    :param number: The number of analyses to return
    """
    resp = utils.ps_core(config, staging, number)
    data = [(a.uuid, a.status, a.submitted_at) for a in resp.analyses]
    click.echo(tabulate(data, tablefmt="fancy_grid"))


@cli.command(help="Display the most recent analysis jobs and their status")
@opts.config_opt
@opts.staging_opt
@opts.interval_opt
def top(config, staging, interval):
    """Return a list of the most recent analyses as a pretty table and update it continuously.

    :param config: The configuration file's path
    :param staging: Boolean whether to use the MythX staging deployment
    :param interval: The refresh interval for table updates
    """
    while True:
        resp = utils.ps_core(config, staging, 20)
        click.clear()
        data = [(a.uuid, a.status, a.submitted_at) for a in resp.analyses]
        click.echo(tabulate(data, tablefmt="fancy_grid"))
        time.sleep(interval)


@cli.command(help="Submit a new analysis job based on source code, byte code, or both")
@opts.config_opt
@opts.staging_opt
@opts.bytecode_file_opt
@opts.source_file_opt
@opts.solc_path_opt
@opts.no_cache_opt
def check(config, staging, bytecode_file, source_file, solc_path, no_cache):
    """Submit a new analysis job based on source code, byte code, or both.

    :param no_cache: Disable the API's result cache
    :param config: The configuration file's path
    :param staging: Boolean whether to use the MythX staging deployment
    :param bytecode_file: A file specifying the bytecode to analyse
    :param source_file: A file specifying the source code to analyse
    :param solc_path: The path to the solc compiler to compile the source code
    """
    c = utils.recover_client(config_path=config, staging=staging, no_cache=no_cache)
    if bytecode_file:
        with open(bytecode_file, "r") as bf:
            bytecode_f = bf.read().strip()
        # analyze creation bytecode only
        resp = c.analyze(bytecode=bytecode_f)
    elif source_file:
        with open(source_file, "r") as source_f:
            source_content = source_f.read().strip()
        compiled = utils.compile_from_source(source_file, solc_path=solc_path)
        if len(compiled["contracts"]) > 1:
            click.echo(
                (
                    "The PythX CLI currently does not support sending multiple contracts. "
                    "Please consider using Truffle Security at "
                    "https://github.com/ConsenSys/truffle-security or open a PR to PythX "
                    "at https://github.com/dmuhs/pythx/. :)"
                )
            )
            sys.exit(1)

        for _, contract_data in compiled["contracts"].items():
            bytecode = contract_data["bin"]
            source_map = contract_data["srcmap"]

        sources_dict = copy(compiled["sources"])
        sources_dict[source_file]["source"] = source_content
        resp = c.analyze(
            bytecode=bytecode,
            source_map=source_map,
            source_list=compiled["sourceList"],
            sources=sources_dict,
            solc_version=compiled["version"],
        )
    else:
        click.echo("Please pass a bytecode or a source code file")
        sys.exit(1)

    click.echo("Analysis submitted as job {}".format(resp.analysis.uuid))
    utils.update_config(config_path=config, client=c)


@cli.command(help="Check the detected issues of a finished analysis job")
@opts.config_opt
@opts.staging_opt
@opts.uuid_arg
def report(config, staging, uuid):
    """Retrieve the issue report and resolve the source maps to their file locations.

    :param config: The configuration file's path
    :param staging: Boolean whether to use the MythX staging deployment
    :param uuid: The analysis job's UUID
    """
    c = utils.recover_client(config_path=config, staging=staging)
    resp = c.report(uuid)

    utils.echo_report_as_table(resp)

    utils.update_config(config_path=config, client=c)


@cli.command(help="Submit a Truffle project to MythX")
@opts.config_opt
@opts.staging_opt
@opts.no_cache_opt
def truffle(config, staging, no_cache):
    """Send a compiled truffle project to the API and display the reports.

    This assembles multiple analysis requests based on the built truffle compile artifacts,
    sends them to the API, polls until they are done, and displays the report results.
    """
    c = utils.recover_client(config_path=config, staging=staging, no_cache=no_cache)

    jobs = []
    job_to_name = {}
    for artifact_file in find_artifacts(os.getcwd()):
        LOGGER.debug("Processing %s", artifact_file)
        with open(artifact_file) as af:
            artifact = json.load(af)

        contract_name = artifact.get("contractName")
        bytecode = artifact.get("bytecode")
        deployed_bytecode = artifact.get("deployedBytecode")
        source_map = artifact.get("sourceMap")
        deyployed_source_map = artifact.get("deployedSourceMap")
        resp = c.analyze(
            contract_name=contract_name,
            bytecode=bytecode if bytecode != "0x" else None,
            deployed_bytecode=deployed_bytecode if deployed_bytecode != "0x" else None,
            source_map=utils.zero_srcmap_indices(source_map) if source_map else None,
            deployed_source_map=utils.zero_srcmap_indices(deyployed_source_map) if deyployed_source_map else None,
            sources={
                path.basename(artifact.get("sourcePath")): {
                    "source": artifact.get("source"),
                    "ast": artifact.get("ast"),
                    "legacyAST": artifact.get("legacyAST")
                }
            },
            source_list=[artifact.get("sourcePath")],
            solc_version=artifact["compiler"]["version"]
        )
        jobs.append(resp.uuid)
        job_to_name[resp.uuid] = contract_name
        click.echo("Submitted: {} ({})".format(resp.uuid, contract_name))

    for uuid in jobs:
        click.echo("Waiting: {} ({})".format(uuid, job_to_name[uuid]))
        while not c.analysis_ready(uuid):
            time.sleep(3)
        click.echo("Done: {} ({})".format(uuid, job_to_name[uuid]))

    for uuid in jobs:
        # print the results
        utils.echo_report_as_table(c.report(uuid))
        click.echo()
        time.sleep(3)

    utils.update_config(config_path=config, client=c)
