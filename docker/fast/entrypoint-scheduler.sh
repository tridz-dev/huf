#!/usr/bin/env bash
# Entrypoint for the scheduler service.
set -e

exec bench schedule "$@"
