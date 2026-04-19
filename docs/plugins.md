# Plugin Guide

Plugins are loaded through Python entry points in the `fluxrules.plugins` group. Each plugin
exports a registration callable that receives a `PluginRegistry`.
