# Agentic PWAD QA: An Autonomous LLM-Driven Testing Framework for Doom Maps

## Abstract

Quality assurance for game maps is a resource-intensive process that suffers from inconsistent coverage and limited traceability. This project presents a proof-of-concept framework that uses Large Language Model agents as autonomous playtesters for Doom maps, exploring the feasibility of AI-driven map quality assurance.

The framework combines static map analysis, an autonomous agent-based playtesting loop, and automated report generation. Users upload a Doom map, configure a test run, and the system handles the rest — analyzing the map's structure, launching an LLM agent that navigates and interacts with the map while recording its reasoning, and producing a structured QA report with detected defects and an overall quality verdict. The agent maintains decision memory within a run enabling cumulative knowledge of map hazards.

Evaluation across multiple runs and configurations demonstrates a working end-to-end pipeline while highlighting current limitations of language models in sequential game control. By modeling map testing as an autonomous, evidence-generating process, this work establishes a foundation for agentic approaches to game quality assurance.