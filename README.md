# MINA — My Intelligent Navigation Assistant

**A Voice-First Agentic AI Assistant for Busy Parents**

Carnegie Mellon University — Agentic AI Capstone Project

## Project Overview

MINA is a voice-first AI assistant designed to help busy
parents manage everyday family responsibilities through
conversational interaction and coordinated tools.

The prototype combines task management, calendar operations,
shopping lists, family scheduling, route planning, reminders,
and optional local conversation memory.

## Motivation

Family responsibilities often involve fragmented schedules,
multiple applications, and repetitive planning decisions.

MINA explores how an AI-assisted system can reduce this
coordination burden while preserving user control.

## Core Capabilities

- Voice and text-based interaction
- Calendar reading and event creation workflows
- Shopping list management
- Family Hub and saved places
- Multi-stop route planning
- Weather-aware planning support
- Standalone local reminders
- Optional persistent conversation memory
- Multi-turn information collection
- Confirmation and cancellation for supported write actions

## Technology

- Python
- Streamlit
- OpenAI API integration
- Google Calendar API
- Local persistence
- External routing and geocoding services

## Project Status

Version: 2.15.4

Status: Final Integrated and Validated Prototype

The prototype was developed iteratively, with documented
fixes, feature extensions, and user acceptance testing.

A clean-install verification of this public repository
is still pending.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Installation](docs/INSTALLATION.md)
- [Running MINA](docs/RUN.md)
- [Tests](docs/TESTS.md)
- [Results](docs/RESULTS.md)
- [Development History](docs/DEVELOPMENT_HISTORY.md)

## Safety and Privacy

MINA uses explicit confirmation for supported write actions.

Certain features require external APIs or user-provided
credentials. Local user data and credentials must not
be committed to the public repository.

Local conversation memory is optional and is not encrypted
at rest in the current prototype.

## Limitations

MINA is a research and educational prototype, not a
production service. Some features depend on external
services, configuration, and user-provided information.

Local reminders do not provide background push notifications.

## License

License to be determined before public publication.
