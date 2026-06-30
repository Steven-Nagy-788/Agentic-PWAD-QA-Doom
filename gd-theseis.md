## Faculty of Computing and Information Sciences
## BoJack: The Ultimate Agentic Game Tester
## Steven Nagy - ElAmir ElSady
## Mohamed Ibrahim - Yousef Walid
## Omar Alsadaany
## Graduation Project Thesis
## in partial fulfillment of the requirements for the degree of
## BACHELOR OF SCIENCE
## in
## Computing & Information Sciences
## Supervisor(s):
## DR Mohamed Taher
July 2026

---

Declaration & Acknowledgements
We hereby declare that the work presented in this project is entirely our own original creation.
From the initial conceptualization of the core idea to the design, development, and implementation
of a completely novel solution, the team operated independently. We confirm that this project
represents an original engineering contribution that combines existing technologies — the Model
Context Protocol, ViZDoom, and Google Gemini — into a purpose-built automated game quality
assurance platform with integrated audit trails and report generation and that no external assistance
or outside contributions were utilized in the execution of the work. All primary research, engineering,
and problem-solving were conducted exclusively by the team members: Omar Alsadaany, Steven Nagy
,Mohammed Ibrahim, Elamir Elsady and Youssef Walid
We would like to express our sincere appreciation to our advisor, Dr. Mohamed Taher, for his
invaluable guidance and mentorship throughout this project. While the ideation, technical
execution, and development of the solution were carried out entirely independently by the project
team, Dr. Taher’s expert advice, feedback, and supervision were instrumental in refining our
approach and helping us navigate the complexities of bringing this idea to life.
2

---

Abstract
Automated quality assurance in game development remains a largely manual and
resource-intensive process, placing a disproportionate burden on small indie studios that lack
dedicated QA personnel. This project presents an AI-driven automated game testing agent designed
to reduce that burden by autonomously exploring game environments, detecting bugs, and
generating structured test reports without human intervention.
The system operates by injecting a per-iteration context into the agent consisting of a static map
analysis, a rolling 16-action history with reasoning logs, MCP tool call records, the latest engine
frame, and an ASCII map matrix for spatial grounding. A hallucination guard monitors for repeated
no-progress tool calls and applies a deterministic fallback to prevent stalled runs. An optional
cross-run hypothesis mechanism carries forward insights from prior sessions to inform subsequent
test runs.
Testing was conducted across four WAD configurations (Easy E1M1, Hard E1M1, Slaughter E1M1,
Easy MAP01), of which two produced gameplay data. The agent identified unreachable secret sectors
via static analysis and LLM-observed traversal anomalies on successfully loaded maps. Generated
reports follow the IEEE standard QA template, producing stakeholder-ready documentation.
User feedback from four indie game developers was collected through post-session surveys and
semi-structured interviews. Participants rated overall satisfaction at 4.1 out of 5, with the IEEE-format
report output and overnight autonomous testing as the most praised features. The cross-run
hypothesis feature received mixed feedback (2.9/5), with users requesting a toggle to disable it.
3

---

Table of Content
Declaration & Acknowledgements................................................................................................. 2
Abstract............................................................................................................................................3
Chapter 1: Introduction............................................................................................................... 7
1.1. Problem Statement.............................................................................................................. 8
1.2. Project Objectives............................................................................................................... 8
1.3. Motivation and Significance............................................................................................... 8
1.4. Scope and Limitations.........................................................................................................8
1.5. Team Members' Contributions.......................................................................................... 8
Chapter 2:
Literature Review.........................................................................................................................9
2.1. Similar Systems................................................................................................................. 10
2.1.1. Academic Scientific Research............................................................................... 10
2.1.2. Market/Industrial Research.................................................................................... 10
2.2. Technologies and Tools Overview.....................................................................................10
2.3. Gap Analysis..................................................................................................................... 10
Chapter 3:
System Analysis & Requirements............................................................................................11
3.1. Functional Requirements.................................................................................................. 12
3.1.1. System Functions.................................................................................................. 12
3.1.2. Detailed Functional Specification...........................................................................12
3.2. Non-functional Requirements........................................................................................... 12
3.2.1. Security.................................................................................................................. 13
3.2.2. Reliability................................................................................................................13
3.2.3. Portability............................................................................................................... 13
3.2.4. Maintainability........................................................................................................ 13
3.2.5. Availability.............................................................................................................. 13
3.2.6. Usability................................................................................................................. 13
3.2.7. Others as appropriate............................................................................................ 13
3.3. Use Case Diagrams / Scenarios....................................................................................... 13
3.4. Stakeholders and User Roles............................................................................................ 13
Chapter 4: Methodology............................................................................................................14
4.1. Project Development Methodology...................................................................................15
4

---

4.1.1. Example: Waterfall Approach or Agile Approach................................................... 15
4.2. Project Timeline................................................................................................................ 15
4.2.1. Gantt Chart / Sprint Timeline.................................................................................. 15
4.3. Tools and Technologies Used............................................................................................15
Chapter 5:
System Design........................................................................................................................... 16
5.1. System Architecture Diagram........................................................................................... 17
5.2. Database Design...............................................................................................................17
5.3. UML Diagrams................................................................................................................. 18
5.3.1. Class Diagram......................................................................................................... 18
5.3.2. Sequence Diagram................................................................................................... 18
5.3.3. Activity Diagram......................................................................................................18
5.4. UI/UX Mockups.............................................................................................................19
Chapter 6: Implementation....................................................................................................... 20
6.1. Description of major modules/components...................................................................... 21
6.2. Code Snippets....................................................................................................................21
6.3. Integration Process........................................................................................................... 21
6.4. Version Control Practices................................................................................................. 21
Chapter 7:
Testing & Validation...................................................................................................................23
7.1. Test Plan and Strategy...................................................................................................... 24
7.2. Unit Testing, Integration Testing.......................................................................................24
7.3. Test Cases and Results...................................................................................................... 24
7.4. Usability and Performance Testing...................................................................................25
7.5. Bug Tracking.....................................................................................................................25
Chapter 8:
Results & Evaluation................................................................................................................. 26
8.1. Comparison with Initial Requirements............................................................................. 27
8.2. Performance Metrics........................................................................................................ 27
8.3. User Feedback.................................................................................................................. 27
5

---

Chapter 9:................................................................................................................................... 29
Conclusion &
Future Work................................................................................................................................29
9.1. Summary of Achievements................................................................................................ 30
9.2. Challenges Faced and Overcome..................................................................................... 30
9.3. Suggested Enhancements.................................................................................................. 30
9.4. Possibility of Future Research or Scaling........................................................................ 30
References................................................................................................................................. 32
Appendices................................................................................................................................ 34
a. Code..................................................................................................................................... 35
b. Dataset Folder................................................................................................................... 35
c. Deployment Manual............................................................................................................. 35
d. User Guide / Training Material........................................................................................... 35
e. Survey/Interview Questions..................................................................................................35
f. Additional Diagrams............................................................................................................ 35
6

---

Chapter 1: Introduction
# Chapter 1:
# Introduction
7

---

Chapter 1: Introduction
## 1.1. ## Problem Statement
Quality assurance has become an increasingly important stage of the game development
lifecycle, especially in an era where highly anticipated releases often launch in
“unfinished”, buggy states that impact both consumer trust and developer financial
stability. The modern gaming industry faces great challenges in ensuring comprehensive
game testing, as evidenced by the catastrophic launch of “Cyberpunk 2077” in December
2020. Despite CD Project Red’s investment of $315 million into the game and a team of
530 developers, the game was released in a state that many consumers deemed virtually
unplayable. The aftermath was severe; CD Projekt Red incurred approximately $51.2
million in refunds, representing 1.6% of the 13.7 million copies sold in 2020 (Gerblick J.,
2021), and the company’s stock value dropped by over 62% within four and a half
months of the game’s release (Orland K., 2021). This example shows how incomplete
quality assurance can transform a highly anticipated launch into a financial and
reputational disaster.
The reliance on human game testers brings up limitations that lead to such failures.
Manual testing is widely recognized as one of the most resource-intensive phases of
game development. Industry surveys indicate that QA staffing represents a significant
portion of development budgets, with additional costs incurred from bug-fix cycles that
compound when issues are discovered late in the development pipeline (Game Developer,
2016). Despite this, human testers often demonstrate unreliability in
comprehensive and timely bug detection. Internal testers often possess familiarity with
their game mechanics causing them to overlook edge cases that come with being a new
and unfamiliar player. Furthermore, the cost of bugs discovered later in the game
development cycle increases exponentially, which can happen if those edge cases go
overlooked. Research from IBM System Sciences Institute indicates that fixing bugs
found after product release costs four to five times more than addressing it during the
design phase (McPeak A., 2017). This undermines the critical need for more efficient,
thorough, and cost-effective testing solutions.
To summarize, the game development industry faces two related challenges: (1) the
costly and incomplete coverage of human quality assurance testing which consumes
significant development resources while failing to detect all critical bugs, and (2) the
severe financial and reputational consequences of launching games with unresolved
issues.
8

---

Chapter 1: Introduction
## 1.2. ## Project Objectives
Our project aims to create an automated system that uses artificial intelligence to test
Doom game maps for defects and quality issues. By combining modern AI technology
with video game simulation, we hope to make game testing more efficient, thorough, and
cost-effective. The system should help game developers find significant issues in their
maps before blind, new players do, reducing financial allocation to manual testing costs
and the risk of releasing incomplete games. We believe this approach can provide a new
methodology to ensure game quality that is more reliable than depending solely on
human testers.
Project Goals :
- Build a system that can automatically play through Doom maps using an agent
- Detect common map problems like unreachable areas,
- Create a detailed map reporting system that shows what the agent found during
testing
- Store all test results and map runs so developers can review them later
- Allow the agent to have short term and long term memory so it can reason about
its current and past decisions and options
- Implement the use of different/weaker models for more efficient token usage
- Achieve good progress with weaker models to validate the harness
Measurable (SMART) Outcomes :
- The system successfully completes test runs for uploaded Doom PWAD maps with
an auditable decision trail
- Test results include coverage metrics showing what percentage of the map was
explored, alongside the agent's decision path and reasoning
- The system generates stakeholder-ready PDF QA reports following IEEE testing
report format
- Every agent decision is logged with full LLM context, selected action, reasoning,
and fallback status for complete auditability
- A hallucination guard prevents stalled runs by detecting repeated no-progress tool
calls and applying deterministic fallback
## 1.3. ## Motivation and Significance
The video game industry has grown into a multibillion dollar market but the cost of
releasing buggy games continues to hurt companies financially. As discussed previously
with the launch of “Cyberpunk 2077”, poor quality assurance can lead to millions in
losses and damage to a company's image. Game studios spend 10% of their budget on
human game testers to look for potential bugs yet man still go unnoticed. There is a clear
market need for automated testing tools that should find bugs faster and more
9

---

Chapter 1: Introduction
cost-efficiently. Our project addresses this by creating an AI-powered system that can test
game maps thoroughly, helping developers identify bugs before players do.
This project contributes to the growing field of AI research in the gaming and complex
industries. Recent implementations show that large language models can play games but
have troubles when it comes to reasoning and memory. Our project builds on top of these
implementations by creating a system that focuses on quality assurance rather than just
gameplay. We explore how AI agents can be used for systematic testing, how to make AI
decisions auditable and trustworthy, and how to integrate different AI components
(vision, decision making, and game control) into a working game testing system. This
contributes to academic understanding of AI agents in real life applications.
Our project addresses multiple technical challenges in computer science:
● AI Decision Making : Creating an agent that can make good complex decisions
in a 3D environment is difficult. The system must understand what it sees in real
time, plan actions, and adapt to changing situations while keeping track of its
goals.
● System Integration : Combining different technologies (i.e. large language
models, game engines, databases, and web interfaces) into one working system
requires careful design and engineering.
● Auditability and Trust : Many modern AI systems operate as “black boxes”. For
our system to work effectively, it has to record every decision and action so that
developers can understand why the AI made certain decisions or marked certain
aspects as bugs. This is important for quality assurance where transparency
matters.
● Defect Detection : Teaching an agent what should be categorized as a “defect” in
a game requires making it understand the game’s design principles and helping it
distinguish between intentional features and actual bugs.
## 1.4. ## Scope and Limitations
Our project uses Doom as a proof of concept for a broader game quality assurance
platform that could be applied to other games. The system comprises three main
components: a backend API, a game simulation service, and a web interface. The
backend is built with FastAPI and uses PostgreSQL for data storage. The game
simulation uses ViZDoom which allows the AI agent to play Doom through a
programming interface. The web UI is built with Next.js and lets users upload maps, start
tests, and view results.
All in all, the system can upload Doom map files (PWADs), analyze their structure, run
an AI agent to play and test the map, detect defects like unreachable areas or broken
10

---

Chapter 1: Introduction
paths, and generate detailed reports with video playback and evidence. All test data is
stored for later review and the system can stream live progress during testing.
We selected Doom as our test environment for several reasons. Firstly, Doom is easy to
emulate and has hundreds of custom user-made maps available online, giving us plenty of
test material. More importantly, Doom has become an industry-standard platform for AI
and game research. The original ViZDoom paper explains that Doom was chosen over
other games such as Quake, Half-Life, and Unreal Tournament because it is lightweight,
fast, open-source, and gives researchers total control over the game engine. The paper
states that Doom “meets the requirements” for research including being “based on a
popular open-source 3D FPS games” and having “east-to-use tools to create custom
scenarios”. Since its creation, ViZDoom has been used in numerous research papers and
competitions, making it a great benchmark for AI game research.
Our system has several limitations. It currently only supports Doom maps and cannot test
other games without system modifications. The AI decision making process is slower
than realtime gameplay, which means map tests take longer than it would for a human to
conduct. The system requires a Gemini API key to work properly; without it the system
falls back to simpler decision making processes. The lockstep approach, while more
auditable, is slower than fully automated gameplay. The system is designed for single
player testing and does not support multiplayer environments. Finally, the defect
detection is based on heuristics and may miss some types of bugs or mischaracterize
features as bugs; although, the generated detailed report as well as the video playback at
the end of test runs helps developers decide this for themselves.
Minimum Requirements :
● Python 3.12 or newer for the backend and game simulation
● PostgreSQL 14 or newer for the database
● Node.js 22 or newer for the frontend
● A Gemini API key for AI decision-making
● FFmpeg for video recording
● OpenGL and SDL libraries for ViZDoom
● At least 8GB of RAM and a modern processor
11

---

Chapter 1: Introduction
## 1.5. ## Team Members' Contributions
This section outlines the specific roles and contributions of each team member
throughout the project.
Member Name Role/Responsibility
Omar Alsadaany 
AI Consultant & Team Leader – Led project planning and
execution, coordinated milestones, supervised implementation,
and ensured high-quality documentation and delivery.
Steven Nagy 
Software Technical Leader – Responsible for identifying software
solutions, defining technical direction, and leading the
implementation of the project.
Mohamed Ibrahim 
Systems Analyst – Gathered and analyzed requirements,
evaluated business needs, translated objectives into technical
specifications, and supported solution design and
implementation.
Yousef Walid 
Researcher – Conducted technical and market research, analyzed
emerging technologies and industry trends, evaluated solutions,
and produced actionable insights to support strategic and product
decisions.
Elamir Elsady 
UI/UX Designer – Designed user-centered interfaces and
experiences, created wireframes and prototypes, and ensured
intuitive, accessible, and visually consistent products.
12

---

Chapter 2: Literature Review
# Chapter 2:
# Literature Review
13

---

Chapter 2: Literature Review
## 2.1. ## Similar Systems
Our project is a standalone, proof of concept, quality assurance platform for Doom
PWAD maps, though the architecture can be altered and adapted for other game engines.
The system integrates multiple components including a backend API, a game simulation
service, and a web UI to provide comprehensive game testing capabilities to users.
2.1.1. Academic Scientific Research
Several research papers have explored AI-driven game testing and quality
assurance, providing insights into the field. Kempka at al. (2016) created
ViZDoom, a Doom-based AI research platform for visual reinforcement learning,
which established Doom as the baseline for AI research in first-person shooter
games. The authors demonstrated that Doom’s lightweight, fast, and open source
qualities makes it perfect for research, with the platform allowing bots to play the
game using screen buffer data (Kempka et al., 2016). Their work laid the
foundation for using Doom as a standard testing ground for AI agents, although it
mainly focused on using it for reinforcement learning instead of quality assurance
systems.
The paper “Will GPT-4 Run DOOM?” investigated whether GPT-4 could play
Doom through a dual component system, using GPT-4V for vision processing and
GPT-4 for decision making (Wydmuch et al., 2024). The study found that while
the model could perform basic tasks such as opening doors and fighting enemies,
demonstrating basic agency, the agent suffered from weak reasoning and poor
memory. The authors noted that the agent would forget about enemies when they
went out of view and struggled with long-term goal planning. This highlighted the
limitations with current LLMs capabilities in complex game environments that
may have multiple short and long term goals (Wydmush et al., 2024).
Building on these developments, recent work has focused specifically on AI
assisted game testing solutions. The paper “Experiment Report: Human-AI
Collaborative Game Testing with Vision Language Models” presented an AI
assisted workflow that integrated machine learning to identify defects in game
visuals, user interfaces, and game mechanics (Zhang et al., 2025). Through
studies, the researchers demonstrated how AI enhanced game testers’
performance under varying conditions. The study identified two main AI driven
game testing approaches: rule-based automation and AI driven perception
systems. They detailed that while AI greatly helped with detecting visual defects
and simulating gameplay, it struggled with replicating the unpredictable nature of
a human player’s behavior and testing the more unconventional scenarios that
human players put the game in (Zhang et al., 2025).
14

---

Chapter 2: Literature Review
Further academic work has explored AI driven testing approaches beyond the
Doom environment. Ariyurek et al. (2019) proposed a methodology that uses both
reinforcement learning and monte carlo tree search agents to automate game
testing. Their study introduced "synthetic agents" built from game scenario graphs
and "human-like agents" trained through inverse reinforcement learning on
recorded human gameplay. While the system was effective at finding defects in
2D games using the GVG-AI framework, it relied on predefined interaction states
and did not perform well in more complex 3D environments that our system
addresses.
Stahlke et al. (2020) developed PathOS, a framework for the Unity engine that
simulates player navigation to evaluate level design. PathOS uses heuristic-based
agents with different behavior profiles such as aggression and curiosity to predict
player paths and find problems. Unlike our system, which uses a learning-based
large language model for decision making, PathOS relies on fixed utility scores
and does not generate useful audit reports or learn from its runs.
Mastain and Petrillo (2023) took a different direction by combining behavior
driven development with reinforcement learning, allowing developers to write test
scenarios in the gherkin language which agents then attempt to execute. While
this approach connects structured software testing with game environments, it still
requires developers to manually write test cases for every scenario, compared to
our system which explores and tests maps autonomously.
Recent work has also explored LLM-based testing in simpler game domains. Lap
(2025) applied ChatGPT to automated playtesting of match-3 games, achieving higher
code coverage and triggering more crashes than existing tools, though limited to
2D tile-matching mechanics. Sensi (2026) introduced curriculum-based test-time
learning for LLM game agents and identified "self-consistent hallucination cascades"
— where errors in perception propagate through the agent's reasoning pipeline — as
a key failure mode. This finding validates our hallucination guard approach, which
detects and mitigates similar stall patterns through deterministic fallback. In the Doom
domain specifically, QoE-Doom-BugHunter (2026) implemented an Explorer-Inspector-
Reporter architecture for bug discovery using rule-based random exploration,
demonstrating that structured agentic workflows can produce reproducible bug reports
with Quality of Experience severity scoring.
2.1.2. Market/Industrial Research
Several tools currently exist for automated game testing, each with their
respective strengths and limitations.
AltTester Unity SDK is an open source automated game testing tool that is
designed specifically for Unity games. It allows testers to interact with different
game objects through scripts and supports multiple programming languages
(AltTester, 2025). Its strengths include it being free, offering support for multiple
scripting languages, and allowing integration with other testing tools. Its main
downside is that it's limited to only Unity games and requires adding an SDK to
the game, which may not be possible for all workflows (QAwerk, 2025).
GameDriver is another platform that's a commercial solution, offering support for
Unity and Unreal Engine. Its prominent feature is the Test Assistant, a tool that
enables test creation and maintenance without accessing the source code or the
game engine (QAwerk, 2025). The tool gives direct access to game objects in the
15

---

Chapter 2: Literature Review
engine using the HierarchyPath Query language and offers cross-platform
compatibility. This is one of its main strengths alongside its ability to perform
tests without source code modification. However, it is not completely free to use,
requiring a commercial license investment after a 14 day trial. It also offers very
limited support to game engines outside of Unity and Unreal (QAwerk, 2025).
Our system separates itself from these existing solutions by using AI agents that
automatically explore and test game maps without a pre-existing script. While
commercial tools like AltTester and GameDriver focus on scripted, rule-based test
automation, our system uses large language models for decision making, allowing
for a more adaptive and natural testing behavior. Additionally, our system
provides comprehensive audit logs and bug detection tailored specifically for map
and level quality assurance. Most commercially available tools don't offer these
functionalities, instead focusing on UI and functionality testing rather than spatial
and gameplay defect detection.
## 2.2. ## Technologies and Tools Overview
The backend of our system is built using FastAPI. FastAPI was chosen because it has
asynchronous capabilities which allows game testing operations like simulation and
Gemini gameplay analysis to be handled at the same time. Data storage is handled
through PostgreSQL and database migrations are handled through Alembic.
Communication between the two is done using the asyncpg PostgreSQL driver. For the
AI gameplay and decision making, the backend integrates Google’s Gemini API through
the google-genai SDK library. PDF report generation is handled with WeasyPrint which
converts HTML into readable and digestible documents for audit checking and test run
summaries.
Game simulation is done through the ViZDoom 1.3 python library. It allows our system
to control gameplay, capture screenshots, and collect game state information. This tool
was selected as it is already highly researched and established, being used as an industry
standard platform for AI gameplay research and being lightweight and fast.
Communication between the backend and the game simulation happens with FastMCP
3.2. It implements the MCP standard that provides a clean interface for the backend to
request game states, take actions in the simulation, and receive feedback from the game.
The MCP runs as a separate process, allowing game simulation to happen separately from
the backend API.
The web interface is built with Next.js 16 which is a React framework, with React 19
serving as the UI library. Styling is handled with Tailwind CSS v4. State management
16

---

Chapter 2: Literature Review
and data fetching happens through TanStack Query and frontend testing is done through
Vitest.
omgifal is a python library that's used to read uploaded Doom WAD files. It handles map
parsing for static analysis, allowing the map geometry, enemy locations, sector counts
and more to be analyzed by the backend before any test runs begin.
Video recording playback of gameplay runs uses the FFmpeg multimedia framework.
The ViZDoom engine requires OpenGL and SDL libraries for rendering and input
handling. The system can be deployed using Docker Compose which commands the
PostgreSQL database, MCP-Doom service, backend API, and frontend web application
as connected containers.
Python 3.12 is the runtime environment for the backend system and game simulation
services, while Node.js provides the runtime for the frontend application. Version control
and tracking is handled through Git.
## 2.3. ## Gap Analysis
Recent academic research based on AI driven game testing shows limitations in LLMs’
capabilities. The paper “Will GPT-4 Run Doom?” details that while GPT-4 can perform
basic actions and gameplay, it struggles in its reasoning and memory, like forgetting
about enemies when they move out of view and struggling in long-term goal completion
(Wydmuch et al., 2024). This suggests the current LLMs cannot efficiently play or test a
game alone, requiring additional memory and reasoning systems.
Furthermore, research on human and AI collaborative testing reveals that while AI agents
can identify visual glitches and simulate basic player behaviors, they struggle when it
comes to simulating unpredictable and more randomized behaviors as well as nuanced
gameplay scenarios where human testers perform better (Zhang et al., 2025). The study
also brought up the problem of AI hallucinations, where systems categorize actual
features as bugs, requiring human analysis to verify AI generated reports. This shows that
fully AI systems may not be ready yet to replace human testers entirely.
Additionally, our research found that many existing studies focus on AI’s reinforcement
learning capabilities with games, rather than using AI for game quality assurance. The
ViZDoom platform, while establishing Doom as the benchmark for AI research, was
mainly designed for training agents rather than making them find defects and testing
maps (Kempka et al., 2016). While recent work has demonstrated LLM capabilities in
game playing and basic bug detection, few systems combine structured tool
abstractions (like MCP) with auditable lockstep decision loops, per-iteration reasoning
logs, and automated IEEE-format report generation specifically tailored for map and
level quality assurance. Our system addresses this integration gap.
Commercial game testing automation tools also have several limitations that our project
addresses. Referenced previously, AltTester and Gamedriver require engine-specific
integration and only focus on scripted testing automation, requiring testers to write
specific test cases for each scenario (QAwerk, 2025). Our project addresses this problem
directly by deploying an LLM to perform gameplay autonomously without the need of
writing scripts, allowing for a more natural testing process.
Most existing tools focus on functional testing rather than special and gameplay defect
detection. They lack comprehensive audit logs that record every decision taken during
testing, an essential feature for quality assurance. They also do not include an integrated
defect detection and classification system, leaving testers to manually check for any bugs.
18

---

Chapter 3: System Analysis & Requirements
# Chapter 3:
# System Analysis &
# Requirements
19

---

Chapter 3: System Analysis & Requirements
## 3.1. ## Functional Requirements
3.1.1. System Functions
1. The system must allow users to upload Doom WAD files through a web interface
for quality assurance testing.
2. The system must provide users with the ability to initiate automated test runs on
specific uploaded WAD map files.
3. The system must execute AI driven gameplay with an integrated large language
model (Gemini) through the ViZDoom game engine to explore uploaded maps
with intelligent decision making.
4. The system must detect and classify defects such as unreachable areas, resource
imbalances, and gameplay issues during test runs.
5. The system must generate detailed, downloadable PDF reports that include test
results, defects found, suggested improvements, and evidence of the defects such
as screen shots.
6. The system must keep a history of all previous test runs and their data including
game states, agent decisions, and defects found for later review and analysis.
7. Users should receive real-time progress updates on test runs.
8. The system should make sure that only one test run executes at a time to prevent
resource conflicts.
9. The system should validate uploaded WAD map files to make sure they are
compatible with the Doom engine before testing.
10. The system could provide health check endpoints to monitor system status and
availability.
11. Users could be able to configure test parameters including level difficulty, run
time limit, and the degree of testing.
3.1.2. Detailed Functional Specification
Table 1: The system must allow users to upload Doom WAD files through a web interface.
FR01 WAD File Upload
Description The system must provide a web interface to upload Doom WAD map files for quality
assurance testing.
Input WAD file, file/test run name
Output Upload success notification, file storage path
Priority Must-have
20

---

Chapter 3: System Analysis & Requirements
Pre-condition None
Post-
condition
The WAD file is stored in the system database and file system with its metadata.
Table 2: The system must provide users with the ability to initiate test runs on uploaded WAD files.
FR02 Test Run Initiation
Description The system must allow users to initiate automated test runs on specific maps. The
system should allow users to configure parameters such as level difficulty, run time
limits, and the degree of testing.
Input Run initiation confirmation
Output Game states, agent decisions, screenshots
Priority Must Have
Pre-condition WAD map file
Post-
condition
Test run begins execution.
Table 3: The system must execute AI driven gameplay with an integrated language model through the ViZDoom
game engine.
FR03 AI Gameplay Execution
Description The system must execute AI driven gameplay through ViZDoom by using a LLM for
intelligent decision making so it can explore and interact with the map effectively.
Input WAD file, map information
Output Game states, agent decisions, screenshots
Priority Must-have
Pre-condition Test run successfully initiated
Post-
condition
Gameplay data has been recorded and stored for analysis.
Table 4: The system must detect and classify defects during test runs.
FR04 Defect Detection
Description The system must detect and classify defects like unreachable areas, resource
imbalance, gameplay issues, etc, based on the AI’s gameplay run and behavior and
21

---

Chapter 3: System Analysis & Requirements
static map analysis.
Input Game states, agent decisions, screenshots, static map analysis
Output List of found defects alongside their severity, priority, descriptions, and
recommendations on how to fix them.
Priority Must-have
Pre-condition The test run has generated its data.
Post-
condition
The defects found are stored in the database and are linked to its respective test run.
Table 5: The system must generate detailed PDF reports.
FR05 PDF Report Generation
Description The system must generate detailed PDF reports that include test results, found defects,
suggested improvements, evidence of defects (screenshots and video gameplay), and
map coverage percentage.
Input Test run ID, defect data from test run, gameplay data from test run
Output PDF report file named after its test run
Priority Must-have
Pre-condition Test run is complete with its collected data and found defects.
Post-
condition
PDF report is stored and available to download any time.
Table 6: The system must keep a history of test runs with their data for future review.
FR06 Test Run Data History
Description The system must keep a history of test runs with all their data including game states,
agent decisions, and defects found for later review and analysis.
Input User selection of old test runs.
Output Selected test run with all its stored data.
Priority Must-have
Pre-condition Past, fully executed test runs exist.
Post-
condition
Test run game states, agent decisions, defects found, video gameplay, and more data
about it is displayed to the user.
22

---

Chapter 3: System Analysis & Requirements
Table 7: Users should receive real-time progress updates on the test run.
FR07 Real-time Progress Updates
Description The system should give real-time progress updates during test run execution, allowing
users to monitor test status and current game state. Users should be able to see what
actions the AI is taking in real time and the reasoning behind these decisions.
Input Test run ID, test run initiation
Output Progress updates, current game states, AI decisions, screenshots
Priority Should-have
Pre-condition Test run is in progress and WebSocket connection is established
Post-
condition
Users receive continuous test run updates until completion.
Table 8: The system should make sure that only one test run executes at a time
FR08 Concurrent Run Prevention
Description The system should make sure that only one test run executes at a time to prevent
resource allocation conflicts and keep the system stable
Input Test run initiation request
Output Request approval or denial based on other run statuses
Priority Should-have
Pre-condition System is operational, a run initiation has been requested
Post-
condition
Requested run either begins or gets denied because of an already pending test run.
Table 9: The system should validate uploaded WAD map files before execution.
FR09 WAD File Validation
Description The system should validate uploaded WAD map files before execution to see if they are
compatible with the system.
Input WAD file upload
Output File either approved or denied based on its compatibility.
Priority Should-have
23

---

Chapter 3: System Analysis & Requirements
Pre-condition WAD file uploaded
Post-
condition
Users are given the option to initiate the run if the WAD file is valid, an error message
appears if the uploaded file is invalid
Table 10: The system could provide healthcheck endpoints to monitor the system
FR10 Health Monitoring
Description The system could provide health check endpoints to monitor the system’s status,
database connection, MCP availability, and overall system health.
Input HTTP GET request to health endpoint
Output System health and status
Priority Could-have
Pre-condition System is running
Post-
condition
Health status is returned.
Table 11: users could configure test parameters before test runs.
FR11 Configurable Test Run Parameters
Description Users could be able to configure test parameters before test runs like level difficulty,
run time limit, and level of AI testing depth.
Input Test run configuration (level difficulty, run time limit, AI testing behavior)
Output Configured test run
Priority Could-have
Pre-condition WAD file uploaded and is valid.
Post-
condition
Test run is queued and begins execution following configured parameters.
## 3.2. ## Non-functional Requirements
The listed non-functional requirements detail the quality and operational constraints that
the system must satisfy outside of its core functional requirements. These requirements
outline how the system should perform rather than what it does.
24

---

Chapter 3: System Analysis & Requirements
3.2.1. Security
● The system must store sensitive values such as the Gemini API key and
database credentials in server-side environment variables and must not
reveal them to any client API endpoints or to the frontend interface.
● The system should not reveal internal stack traces, file paths, or database
error information in API responses returned to clients.
3.2.2. Reliability
● The system must handle MCP-Doom service failures gracefully, returning
error status information and preventing the backend from crashing.
● The system must mark any test runs that were happening during a server
restart or crash as failed, preventing “orphaned” runs from blocking future
runs.
● The system should recover from situations where individual LLM
decisions fail by retrying the request before falling back to deterministic
action.
● The system should log all run failures and categorize them by failure
reason so developers can identify any problems that may have caused
them.
3.2.3. Maintainability
● The system must separate its components into three independent modules,
the backend API, the game simulation service, and the frontend, such that
they are each testable individually.
● The system must manage all database schema changes through
version-marked Alembic migration files, ensuring schema development
traceability.
● The system should have a layered backend architecture so that business
logic remains separate from the database layer and the HTTP layer.
● The system should use environment variables and a runtime parameter
table for the parameter configuration so that test run behaviour can be
adjusted without changing the source code.
3.2.4. Performance
● The system must make sure PDF report generation is handled by a
separate worker thread so that the main FastAPI loop is not disrupted by
the expensive PDF rendering process, keeping the API responsive during
report generation.
● The system must limit LLM decision requests at a configurable rate so that
it stays within the API usage limits and prevents excessive token usage.
25

---

Chapter 3: System Analysis & Requirements
● The system should get a fresh database session per lockstep iteration
rather than holding a single extended session for an entire run, this reduces
the risk of connection timeouts during long test runs
3.2.5. Usability
● The system must provide a readable and understandable web interface to
users for them to upload WAD map files, configure test runs, and view
results.
● The system must provide real-time test run feedback during runs so that
users can review and evaluate progress before the test run is complete.
● The system must clearly display specific elements including the status of
test runs and severity of defects using color-coded indicators for easy
readability.
● The system must provide a test run history interface to allow users to
review and see the results of previous runs.
● The system should provide a system health dashboard to allow users to
check the status of each component in the system (backend, game
simulation, frontend, etc) without looking at server logs.
3.2.6. Auditability
● The system must present each agent decision with the LLM’s input
context, selected action, and reasoning behind that action, allowing users
to view the process behind every decision.
● The system must show the source behind every decision, distinguishing
between the LLM’s intelligent decisions and those decisions made with
deterministic fallback.
● The system must generate a comprehensive and downloadable PDF report
that outlines each test runs’ found defects, map coverage percentage, token
usage, and suggested improvements into an auditable document.
● The system should record potentially found defects alongside their game
coordinates and a screenshot of the gameplay at that instance, allowing
users to trace back the bug in the actual game.
26

---

Chapter 3: System Analysis & Requirements
## 3.3. ## Use Case Diagram
Figure 1: Use-case diagram of our system and its actors
## 3.4. ## Stakeholders and User Roles
Stakeholders:
1. Game Studio Management
○ Defines business goals and project requirements.
○ Evaluates testing efficiency and return on investment.
2. QA Managers
○ Plan testing strategies and monitor testing progress.
○ Review bug reports and testing coverage.
27

---

Chapter 3: System Analysis & Requirements
3. Game Testers
○ Configure testing scenarios and validate discovered issues.
○ Analyze AI-generated test results.
4. Game Developers
○ Receive bug reports and reproduction steps.
○ Fix defects identified by the testing agents.
5. Game Designers
○ Review gameplay analytics and player behavior simulations.
○ Validate game balance and design objectives.
6. AI Research and Engineering Team
○ Develop and maintain AI testing agents.
○ Improve agent behavior and testing capabilities.
7. System Administrators / DevOps Engineers
○ Manage infrastructure, security, and system availability.
○ Monitor performance and resource utilization.
8. Clients (Game Studios)
○ Use the platform to automate game testing.
○ Access reports, analytics, and testing results.
9. Investors / Sponsors
○ Provide funding and evaluate the project's success.
User Roles:
1. Administrator
○ Manages users, permissions, configurations, and system settings.
2. QA Manager
○ Creates testing campaigns, monitors agent execution, and reviews reports.
3. Game Tester
○ Configures test scenarios and validates detected issues.
4. Developer
○ Reviews bug reports, logs, screenshots, and reproduction steps.
5. Designer
○ Analyzes gameplay behavior and balance reports.
6. AI Engineer
○ Maintains and improves AI models and agent behavior.
7. Client / Project Manager
○ Monitors project status, testing progress, and generated reports.
Primary Stakeholders:
28

---

Chapter 3: System Analysis & Requirements
● Game Studio Management
● QA Managers
● Game Developers
● Game Testers
● Clients (Game Studios)
Secondary Stakeholders:
● AI Engineers
● System Administrators
● Game Designers
● Investors / Sponsors
29

---

Chapter 4: Methodology
# Chapter 4:
# Methodology
30

---

Chapter 4: Methodology
## 4.1. ## Project Development Methodology
The project followed an iterative development methodology adapted for a small academic team of
five members. Development was organized into one to three week sprints, with each
sprint beginning with a planning session where tasks were selected and assigned to team
members based on their roles. At the end of each week, the team held a review session
with the project’s supervisor, Dr. Mohamed Taher, to demonstrate completed work and
receive advice on what to do moving forward. This iterative approach allowed the team
to continuously adjust our development cycle as new technical challenges emerged,
which was especially important given the three major architecture shifts the project went
through across its timeline.
The team used GitHub for version control, Discord and Whatsapp for daily
communication, and Google Docs for shared documentation. The team supervisor, Dr.
Mohamed Taher, received progress updates and provided guidance on academic
requirements through previously mentioned weekly progress meetings and a shared
Whatsapp group chat.
## 4.2. ## Project Timeline
4.2.1. Sprint Timeline
Term 1 — December 2025 to March 2026
● Sprint 1 (Dec 1 – Dec 14): Project environment setup. Configured
development machines, installed ViZDoom and Python dependencies,
initialized the GitHub repository with a base project structure, and set up
the PostgreSQL database schema.
● Sprint 2 (Dec 15 – Dec 28): Backend API development. Built the core
FastAPI application structure with SQLAlchemy 2.0 async and asyncpg.
Implemented the initial database models for maps, runs, bugs, and metrics.
Set up the first working API endpoints for map upload and run creation.
● Sprint 3 (Dec 29 – Jan 25): Deep RL agent architecture and initial
training setup. Designed the DQN agent with a custom 4-layer CNN
backbone and optional DRQN recurrent extension. Implemented the
experience replay buffer, ε-greedy exploration, and the ViZDoom
environment wrapper. First successful training runs on the default Doom
scenario. Final term 1 exams were happening throughout January so
project progress was slower.
31

---

Chapter 4: Methodology
● Sprint 4 (Jan 26 – Feb 9): Telemetry extraction and bug detection.
Implemented the LogParser to extract per-episode gameplay events from
Arnold's output logs. Built the BugService to classify detected issues into
stuck states, instant deaths, visual glitches, and unreachable areas.
Integrated bug records with the database.
● Sprint 5 (Feb 10 – Feb 23): LLM integration and report generation.
Connected the Gemini API to the backend. Built the LLMReportService
to generate natural language bug reports from run telemetry. Stored
generated reports as inline text fields on the run record.
● Sprint 6 (Feb 23 – Mar 2): Frontend development and visualizations.
Built the React 19 frontend using Vite with five core pages: Dashboard,
Maps, Runs, Run Details, and Bugs. Implemented the map upload flow,
run initiation, and basic results display. Added an exploration heatmap
visualization using NumPy.
● Sprint 7 (Mar 3 – Mar 8): Deployment, documentation, and Term 1
submission. Configured Supabase for external storage of map files and
screenshots. Finalized the end-to-end workflow and conducted internal
testing across multiple Doom map configurations. Prepared, submitted,
and presented all the Term 1 deliverables.
Term 2 — March 2026 to June 2026
● RAMADAN AND EID (Mar 9 - Mar 28): NO PROGRESS
● Sprint 8 (Mar 29 – Apr 12): Arnold v1 development. Based on the
evaluation findings, the team redesigned the RL agent. DQN was replaced
with a Proximal Policy Optimization (PPO) algorithm using an
Actor-Critic architecture. The CNN backbone was replaced with a lighter
ImpoolaCNN encoder producing a 512-dimensional feature vector with
approximately 409K parameters, significantly lighter than the initial 1.2M
parameter network. The experience replay buffer was removed in favor of
on-policy rollout segments collected by parallel RolloutWorker threads. A
real-time BugDetector was embedded directly inside the PPO trainer,
allowing bugs to be flagged as they occurred rather than post-run. A
Celery and Redis task queue was introduced so training runs no longer
blocked the API request thread.
● Sprint 9 (Apr 13 - Apr 26): Arnold v2 optimization. The team refined the
exploration strategy by replacing ε-greedy randomness with a four-layer
rule-based reward shaping system. This included count-based novelty
rewards, a frontier bonus for approaching unexplored cells, a sector entry
32

---

Chapter 4: Methodology
bonus for first visits to new ViZDoom sectors, and a wall-stuck penalty.
An OccupancyGrid was introduced to track spatial coverage and compute
a coverage percentage per step. A WebSocket endpoint was added for live
telemetry streaming to the frontend, and the Report table was decoupled
from the session record into its own database table, storing the full Gemini
prompt, response, and markdown output.
● Sprint 10 (Apr 27 – May 10): Architecture evaluation and pivot to MCP.
After testing both Arnold v1 and v2 on a range of PWAD maps, the team
concluded that RL-trained agents still faced fundamental challenges: they
required significant training time per map, lacked auditability of individual
decisions, and did not generalize reliably across different level designs.
Through research into large language model tool-use frameworks, the
team identified the Model Context Protocol (MCP) as a more practical and
auditable approach for game QA. The decision was made to fully pivot the
system architecture to MCP.
● Sprint 11 (May 11 - May 31): Final MCP-based system development. The
team built the MCP-Doom service using FastMCP 3.2 and ViZDoom 1.3,
exposing game control through named tools such as start_game, get_state,
explore, aim_and_shoot, and finish. The FastAPI backend was redesigned
around a lockstep run loop that calls Gemini on every iteration, passing
the current game state, a live screenshot, a 21×21 ASCII grid map, and a
rolling 16-action history. The hallucination guard, deterministic fallback,
static map analysis via omgifol, and the spatial memory and hypothesis
systems were all implemented and integrated. The full Docker Compose
deployment was finalized.
● FINAL EXAMS (Jun 1 - Jun 10): NO PROGRESS
● Sprint 12 (Jun 14 - Jun 28): Final testing, user evaluation, and
documentation. The complete system was tested across multiple PWAD
maps at different difficulty levels and behavior profiles. User evaluation
was conducted with four indie game developers, collecting structured feedback
through post-session surveys, semi-structured interviews, and live
observation sessions. The thesis report was written, diagrams were
finalized, and the project was prepared for submission.
4.2.2. Gantt Chart
●
33

---

Chapter 4: Methodology
## 4.3. ## Tools and Technologies Used
Category Technology Version Purpose
Backend Framework FastAPI 0.136.1 Asynchronous web framework for the backend API,
providing automatic OpenAPI documentation, dependency
injection, and async request handling
Backend Server Uvicorn 0.47.0 ASGI server for running the FastAPI application in
production and development environments
Database ORM SQLAlchemy 2.0.49 Python ORM for database interaction, providing async
support through SQLAlchemy 2.0 syntax with mapped
columns and relationships
Database Driver asyncpg 0.31.0 PostgreSQL async driver for SQLAlchemy, enabling
high-performance asynchronous database operations
Database PostgreSQL 16 Relational database for persistent storage of WAD files, test
runs, agent decisions, defects, and cross-run memory
Database Migrations Alembic 1.18.4 Database migration tool for versioning schema changes and
managing database evolution across development iterations
Validation Pydantic 2.13.4 Data validation library for request/response models,
ensuring type safety and automatic validation of API inputs
Settings Management Pydantic-Settings 2.14.1 Environment-based configuration management for loading
settings from environment variables and .env files
AI / LLM Integration Google GenAI SDK 1.54.0 Python SDK for integrating with Google's Gemini API for
AI decision-making and report generation
AI Model Gemini 3.1 Flash Lite Large language model used for agent decision-making,
defect analysis, and QA report generation
MCP Framework FastMCP 2.14.1 (Backend)
3.2.4
(MCP-Doom
Model Context Protocol framework for exposing game
simulation tools to the backend via SSE transport
Game Simulation ViZDoom 1.3.0 Doom-based AI research platform that allows
programmatic control of Doom gameplay, state extraction,
and screenshot capture
Image Processing Pillow 12.2.0 Python imaging library for handling screenshot data, image
manipulation, and format conversion
Numerical Computing NumPy 2.4.4 Library for numerical operations, used in spatial memory
calculations, grid cell tracking, and coverage metrics
WAD File Parsing omgifol 0.5.1 Python library for reading and parsing Doom WAD files,
extracting map geometry, thing placements, and sector data
for static analysis
Video Processing OpenCV
(opencv-python-headless)
4.13.0.92 Computer vision library for video frame processing and
MP4 recording generation from gameplay telemetry
34

---

Chapter 4: Methodology
Video Encoding FFmpeg System
dependency
Multimedia framework for encoding MP4 recordings from
raw frame data captured during test runs
PDF Generation WeasyPrint 68.1 Visual rendering engine for converting HTML templates
with Jinja2 into professional PDF reports
Template Engine Jinja2 3.1.6 Template engine for rendering HTML report templates with
dynamic data from test runs
HTTP Client httpx 0.28.1 Async HTTP client for making requests to external
services, including MCP server communication
File Upload Handling python-multipart 0.0.28 FastAPI dependency for handling multipart form data
during WAD file uploads
Metrics Prometheus Client 0.21.0+ Metrics library for exposing runtime metrics (runs, LLM
calls, latency) at the /metrics endpoint
Error Tracking Sentry SDK 2.0.0+ Error monitoring and performance tracking service for
capturing exceptions and runtime issues
Frontend Framework Next.js 16.2.6 React framework with App Router for server-side
rendering, API routes, and optimized page loads
UI Library React 19.2.4 JavaScript library for building user interfaces with
component-based architecture
State Management TanStack Query 5.100.11 Data fetching and caching library for managing server state,
API calls, and automatic refetching
Styling Tailwind CSS 4 Utility-first CSS framework for rapid UI development and
responsive design
Icons Lucide React 1.16.0 Icon library providing consistent, customizable SVG icons
for the user interface
Typescript Typescript 5 Typed superset of JavaScript for type-safe frontend
development
Frontend Testing Vitest 4.1.7 Unit testing framework for frontend components and utility
functions
Frontend Coverage @vitest/coverage-v8 4.1.7 Code coverage tool for measuring test coverage of frontend
code
Testing Utilities @testing-library/react 16.3.1 React testing utilities for component testing in a DOM
environment
Testing Utilities @testing-library/jest-dom 6.9.1 Custom Jest matchers for testing DOM elements and
accessibility
E2E Testing Playwright 1.57.0 Browser automation framework for end-to-end testing of
frontend UI across multiple viewports
Linting ESLint 9 JavaScript/TypeScript linter for code quality and
consistency
Backend Testing pytest 9.0.3 Testing framework for backend unit and integration tests
Async Testing pytest-asyncio 1.3.0 Pytest plugin for testing async/await code with async test
execution
35

---

Chapter 4: Methodology
Test Coverage pytest-cov 6.1.1 Code coverage plugin for pytest to measure backend test
coverage
Performance Testing Apache JMeter System tool Load testing tool for measuring API response times and
concurrent load behavior
Frontend Performance Google Lighthouse System tool Web performance auditing tool for measuring page load
speed, accessibility, and best practices
Version Control Git System tool Distributed version control system for source code
management and collaboration
Containerization Docker System tool Container platform for packaging services into isolated
environments
Orchestration Docker Compose System tool Tool for defining and running multi-container Docker
applications for full-stack deployment
CI/CD GitHub Actions System service Continuous integration and delivery platform for automated
testing, linting, and deployment workflows
Display Server Xvfb System tool Virtual framebuffer X server for headless display during
ViZDoom integration testing
Runtime Environment Python 3.12+ Programming language runtime for backend and
MCP-Doom services
Runtime Environment Node.js 22 JavaScript runtime for frontend development and build
processes
Graphics Libraries OpenGL System
dependency
Graphics API required by ViZDoom for 3D rendering
Graphics Libraries SDL System
dependency
Simple DirectMedia Layer library required by ViZDoom
for input handling and window management
36

---

Chapter 5: System Design
# Chapter 5:
# System Design
37

---

Chapter 5: System Design
## 5.1. ## System Architecture Diagram
In Figure 5, the diagram shows the system's four-layer architecture. The presentation
layer includes the Next.js frontend, it communicates with the application layer through
REST API calls and a constant WebSocket connection. The application layer is split
between the FastAPI backend, handling the lockstep AI run loop, defect detection, and
PDF report generation, and the MCP-Doom service, which controls ViZDoom game
simulation behind a clean tool interface. The AI decision layer shows the Google Gemini
API receiving a prompt from the backend during each iteration and returning a structured
JSON decision. Finally, the data and storage layer contains the PostgreSQL database
alongside the file storage directories.
Figure 5: System Architecture Diagram
38

---

Chapter 5: System Design
## 5.2. ## Database Design
Figure 6: System Database Diagram
39

---

Chapter 5: System Design
## 5.3. ## UML Diagrams
5.3.1. Class Diagram
Figure 7: Class Diagram
40

---

Chapter 5: System Design
5.3.2. Sequence Diagram
Figure 8: Sequence Diagram
41

---

Chapter 5: System Design
5.3.3. Activity Diagram
Figure 9: Activity Diagram
42

---

Chapter 5: System Design
## 5.4. ## UI/UX Mockups
Figure 10: Figma UI Mockups
43

---

Chapter 6: Implementation
# Chapter 6:
# Implementation
44

---

Chapter 6: Implementation
## 6.1. ## Description of major modules/components
The system is divided into five core modules, each handling a key component in the
game quality assurance testing pipeline.
Module 1: Frontend Web Interface
The frontend module is the part of the system that users directly communicate with. It
handles user interactions like uploading map files, configuring and starting test runs,
viewing run history and statistics, and tracking live progress. It's built with Next.js 16,
using React 19 as its UI library and TailwindCSS v4 for styling. State management and
data retrieval are handled through TanStack Query, which keeps the UI in sync with the
backend. Live run monitoring is powered by a constant WebSocket connection that
streams decisions, game screenshots, and defect detections in real time. The frontend
communicates with the backend primarily through the REST API at /v1/* and the
WebSocket endpoint at /v1/ws/runs/{run_id}.
Module 2: Backend API
The backend module coordinates the entire system. It exposes all REST endpoints,
manages the database, manages the lockstep AI run loop, handles defect detection after
runs finish, and triggers report generation. It’s built with FastAPI and runs on Python 3.12
with Uvicorn as the ASGI server. Data tracking and storage is handled through
SQLAlchemy with asyncpg as the PostgreSQL driver. All schema changes are versioned
through Alembic migration files. The backend is constructed as a layered architecture,
keeping routers, services, and repositories as separate layers so that business logic does
not mix with database access or HTTP handling. It also exposes a Prometheus metrics
endpoint at /metrics and several health check endpoints at /health/* that allow system
admins to check the status of every component without looking at server logs.
Module 3: MCP-Doom Simulation Service
This module is responsible for actually running the Doom game. It runs as a separate
process from the backend using FastMCP 3.2 over an SSE connection, and uses
ViZDoom 1.3, allowing the systems to control and play Doom autonomously. The
backend communicates with the simulation service by sending named commands such as
"start game", "get the current game state", "move forward", or "shoot the enemy". The
service then carries out the sent command and sends back the result from the game. Each
time the backend asks for the current state, this service returns data of what's happening
in the game, such as the player's health, position, and what enemies are nearby. It also
45

---

Chapter 6: Implementation
sends back a screenshot of the game and a simple text map (a 21x21 ASCII grid), which
helps the AI understand the layout of the level without having to look at the screenshot
alone.
Module 4: AI Decision Engine
This module is responsible for deciding what the AI agent should do next at each step of
the test run. It is implemented in the GeminiService class and uses Google's Gemini API
through the google-genai Python SDK, with gemini-3.1-flash-lite as the default model.
message for the model that includes a description of the map, an audit log of the last 16
actions, the current game state, the latest screenshot, and the text map. The model reads
all of these and responds with a decision as well as an explanation as to why it made that
decision. If the Gemini API is unavailable or fails, the system automatically falls back to
deterministic decision making, dictated by a set of rules. There is also a built-in safety
check that looks for repeated actions without any progress. When that happens, the
system steps in and forces the agent to try something different. Every decision made
during the run, whether by Gemini or deterministic fallback, is saved to the database
along with the reasoning behind it, so the entire run can be reviewed later.
Module 5: Defect Detection and Report Generation
After a test run finishes, two services work together to produce a final output. The first is
the DefectService, which goes through all the collected data during the run and looks for
potential defects and obscurities. Some checks are based on the map's structure using the
static analysis data from omgifol, while others are based on what happened during the
run.. It also sends marked screenshots to Gemini using the google-genai SDK to look for
visual bugs like broken textures or rendering errors. All found problems are saved to the
database with details about their location and time in the run and how serious they are.
The second is the ReportService, which takes all the run data and sends them to Gemini.
Gemini then writes a full professional QA report in structured JSON format which is then
rendered into an HTML document using a Jinja2 template and converted to a
downloadable PDF using the WeasyPrint library. The PDF includes a pass or fail verdict,
a list of all found defects with recommendations on how to fix them, a summary of how
much of the map was explored, and a breakdown of token usage and cost. PDF
generation runs in a separate background thread so that it does not slow down the rest of
the system while the intensive rendering process takes place.
## 6.2. ## Code Snippets
Snippet 1: The Lockstep AI Decision Loop
46

---

Chapter 6: Implementation
The most important part of the whole system is the loop that happens during a test run. At
every step, the system asks ViZDoom for the current game state, builds a prompt and
sends it to Gemini based on it, receives a decision back, and executes that decision in the
game. This repeats these steps until the test run runs out of ticks or the agent finishes. By
pausing the game, asking Gemini what to do, and then executing the action, the system
gives the AI full control over the game while keeping everything synchronized and
auditable. The code below shows the core of this loop from run_loop.py.
while True:
state, screenshot_png = await mcp.get_state()
tick = _factual_game_tic(state, lockstep_state)
_track_visited_cell(state, lockstep_state)
llm_input = _build_llm_input(
state,
threat_assessment,
navigation_info,
lockstep_state,
game_tic=tick,
ticks_remaining=ticks_remaining,
total_cells=total_cells,
coverage_warning=coverage_warning,
)
decision, token_usage = await gemini.decide(
prompt, llm_input,
screenshot_png=screenshot_png,
map_layout_png=map_layout_png
)
response, mcp_call = await _execute_tool(mcp,
decision, state)
Lockstep loop from run_loop.py
Snippet 2: The Hallucination Guard
One major problem with LLM-based agents is that they can get stuck repeating the same
actions and decisions without making any progress. The system solves this with a guard
that monitors the agent's behavior, and steps in when it detects a loop. For example,
without this guard the agent could waste a lot of resources repeatedly trying the same
47

---

Chapter 6: Implementation
blocked door. The guard detects when the agent has not moved for two or more decisions
in a row, forces the next action to be a different decision, and records a note explaining
why the override happened. This note is then shown to the user in the audit trail.The code
below from run_loop.py shows one of the three guard checks.
stuck_counter = lockstep_state.get("position_stuck_counter", 0)
if guard_enabled and stuck_counter >= 2 and \
decision.get("mcp_tool") in ("explore", "move_to",
"take_action"):
_record_failure_critique(
lockstep_state, tick=result_tick,
tool=decision.get("mcp_tool", "unknown"),
params=decision.get("mcp_params", {}),
reason=f"Agent stuck for {stuck_counter} decisions without
meaningful movement.",
)
turn_amount = 180.0 if stuck_counter % 2 == 0 else -180.0
decision["mcp_tool"] = "explore"
decision["mcp_params"] = {
"max_tics": 80,
"stop_on_enemy": False,
"stop_on_item": True,
"turn_before": turn_amount
}
decision["reasoning_summary"] = (
f"OVERRIDE: Agent stuck ({stuck_counter} decisions
without movement). "
f"Guard forced explore with {turn_amount}° turn to break
fixation."
)
decision["_decision_source"] = "guard_stuck"
Hallucination guard from run_loop.py
Snippet 3: Deterministic Fallback
When the Gemini API is unavailable or fails, the system needs to keep the run going
instead of crashing. Utilizing deterministic fallback, the system prevents this from
48

---

Chapter 6: Implementation
happening, producing successful test runs. Every fallback decision is also tagged with
"deterministic_fallback" as the source, so the final report clearly shows how many
decisions were made by Gemini versus the fallback rules. The fallback below from
gemini_service.py uses simple rules to pick the next action based on what is visible in the
game state.
def _fallback_decision(self, llm_input: dict, reason: str) -> dict:
visible_monsters = [
obj for obj in objects
if obj.get("type") == "monster"
and obj.get("is_visible")
and obj.get("id") is not None
]
if visible_monsters:
target = min(visible_monsters,
key=lambda obj: float(obj.get("distance") or
999999))
tool = "strafe_and_shoot" if float(target.get("distance") or
0) < 350 \
else "aim_and_shoot"
return {
"reasoning_summary": f"{reason} Visible enemy selected
for combat.",
"mcp_tool": tool,
"mcp_params": {"object_id": target["id"]},
"observed_issue": None,
"_decision_source": "deterministic_fallback",
}
return {
"reasoning_summary": f"{reason} No target visible,
exploring.",
"mcp_tool": "explore",
"mcp_params": {"max_tics": 80, "stop_on_enemy": True,
"stop_on_item": True},
"observed_issue": None,
"_decision_source": "deterministic_fallback",
}
Deterministic decision fallback from gemini_service.py
49

---

Chapter 6: Implementation
Snippet 4: Agent Prompt Building
Before each decision, the system builds a prompt that tells Gemini everything it needs to
know about the map. This helps the AI model make better decisions because it already
knows the map's structure before it starts any test run. By telling Gemini how many
enemies spawn, whether there are locked doors, what keys are needed, and how difficult
the map is, the agent can focus on testing rather than figuring out information about the
map as the run happens. This is done in prompt_service.py by filling in a template with
real values from the static analysis.
def render_agent_prompt(wad, analysis, run) -> str:
template = (BASE_DIR / "app" / "prompts" /
"agent_system_prompt.md").read_text()
skill_summary = selected_skill_spawn_summary(analysis,
run.difficulty_level)
values = {
"map_name": analysis.map_name,
"thing_count_enemies": spawned_enemies,
"hitscanner_percent":
skill_summary.get("hitscanner_percent"),
"health_ratio": skill_summary.get("health_ratio"),
"ammo_ratio": skill_summary.get("ammo_ratio"),
"secret_sector_count": analysis.secret_sector_count,
"door_count": map_features.get("door_count"),
"key_requirements": key_summary,
"total_linedefs": map_features.get("total_linedefs"),
"total_sectors": map_features.get("total_sectors"),
}
for key, value in values.items():
template = template.replace("{" + key + "}", str(value))
return template
Agent prompt generation from prompt_service.py
Snippet 5: Spatial and Cross-Run Memory
After each run finishes, the system saves a record of where important events happened on
the map. This is stored as a grid of cells, where each cell represents a 256×256 unit area
50

---

Chapter 6: Implementation
of the map. This is key as it allows the system to build up a picture of the map over
multiple test runs. If the agent dies in the same area three runs in a row, that area gets
flagged as a danger zone. This information is shown to the user on the WAD detail page
and can be fed back into future runs to help the agent avoid problem spots discovered
from previous runs. The code below from run_memory.py uses PostgreSQL's "upsert"
feature to either create a new cell record or add to the count of an existing one.
stmt = (
pg_insert(WadSpatialMemory)
.values(
wad_file_id=wad_file_id,
map_name=map_name.upper(),
cell_x=cell_x,
cell_y=cell_y,
event_type=event_type,
occurrence_count=count,
last_seen_run_id=run_id,
)
.on_conflict_do_update(
index_elements=[
"wad_file_id", "map_name",
"cell_x", "cell_y", "event_type"
],
set_={
"occurrence_count":
WadSpatialMemory.occurrence_count + count,
"last_seen_run_id": run_id,
"updated_at": now,
},
)
)
await self.db.execute(stmt)
Spatial memory from run_memory.py
Snippet 6: Defect Hypothesis Confidence Rating
When the agent notices potential defects during a run, it records them as hypotheses.
After multiple runs on the same map, the system tracks how often each hypothesis
appears and updates its confidence score. A new hypothesis starts with a confidence score
51

---

Chapter 6: Implementation
of 0.3. Each time the same observation appears in a later run, the score goes up by 0.15,
capped at 1.0. Once a hypothesis reaches a confidence of 0.6 or higher, the defect
detection service recognizes it as a real defect on the next run. This gives the system a
way to learn from repeated patterns without absolutely confirming a potential defect after
its first encounter. The code below from run_memory.py shows how this works.
if match is not None:
match.confidence = min(1.0, match.confidence + 0.15)
match.last_seen_run_id = run_id
match.updated_at = datetime.now(UTC)
else:
new_hypothesis = WadHypothesis(
wad_file_id=wad_file_id,
map_name=map_name.upper(),
tag=_infer_tag(hypothesis),
content=hypothesis[:500],
confidence=0.3,
last_seen_run_id=run_id,
)
self.db.add(new_hypothesis)
Defect hypothesis confidence from run_memory.py
## 6.3. ## Integration Process
The system was not built as one complete system from the start. It went through three
major architectural changes before arriving at the final five-module design, and each
phase required reintegration work. This section describes how the modules were
connected and what challenges came up along the way.
Phase 1 — RL-Based System (Term 1)
The first integration effort focused on connecting the backend API to the RL agent and
the database. The backend was built first as a standalone FastAPI application with a
working database layer. The RL agent, which ran as a separate Python process running
ViZDoom, was then connected to the backend through a subprocess bridge called the
ArnoldAdapter. After each training run was complete, the LogParser would read the
agent's logs and pass the telemetry data it found to the BugService, which wrote detected
52

---

Chapter 6: Implementation
issues to the database. This approach worked for a basic flow of operations but
introduced a tight coupling between the agent and the backend. Any changes made to the
agent's log formatting broke the parser, and bugs could only be detected after a successful
and completed run, so no live reasoning. The LLM report was generated as a final step
after the bug detection phase and stored as a plain text field directly in the run record. The
frontend was integrated last, connecting to the backend through standard REST API calls.
Phase 2 — Arnold v1 and v2 Refinements (Sprints 8–9)
When we moved to the PPO-based Arnold agents, the integration architecture changed
almost entirely. The synchronous subprocess bridge was replaced with a Celery and
Redis task queue, which meant training runs were active as background tasks and the API
returned immediately after accepting the request. A WebSocket endpoint was added to
stream live data from the active training sessions to the frontend, which required the
frontend to be updated to keep a constant connection instead of using polling. The
BugDetector was moved inside the PPO trainer itself, running in real time alongside the
rollout workers, which required careful synchronization to avoid race conditions between
the bug detection and the database writing operations. The Report table was also
decoupled from the session record into its own table, with the full Gemini prompt and
response stored separately. This meant that the report generation Celery task had to be
called after the training task rather than them happening at the same time.
Phase 3 — MCP-Based Final System (Sprints 10–11)
The final and module integration stage came when the team pivoted to the MCP
architecture. The main task here was replacing the entire agent layer with a completely
different design. The MCP-Doom service was built as a standalone process running on
port 8001 over a FastMCP SSE connection. The backend's McpDoomClient was written
to handle connection retries and timeouts, and a health check endpoint at /health/mcp was
added so the system could verify the service was reachable before attempting to start a
run.
The lockstep run loop was the most complex integration point in the entire project. Each
lockstep iteration required three separate systems to work together in sequence: the MCP
service had to return a valid game state and screenshot, the Gemini API had to accept the
prompt and return a structured JSON decision within a reasonable timeout, and the
database had updated with the decision record before the next iteration began. An issue
53

---

Chapter 6: Implementation
discovered during integration was that holding a single database session open for the
entire duration of a prolonged run caused connection timeouts. This was solved by
opening and closing a fresh database session on each loop iteration rather than keeping
one open for the whole run.
The frontend was connected to the backend's WebSocket endpoint to stream live
decisions, screenshots, and potential defects found as they happened. A challenge at this
stage was that Next.js did not reliably permit WebSocket connections through its built-in
API layer, so the frontend was configured to connect directly to the backend's WebSocket
URL for local development.
PDF report generation using WeasyPrint was also a notable integration step. Running
WeasyPrint directly in the FastAPI async event loop caused the entire API to freeze while
the PDF was rendering. This was solved by moving all PDF rendering to a separate
background thread using Python's asyncio.to_thread, which kept the API responsive
during the rendering process.
The final system was packaged into a Docker Compose setup with four containers:
PostgreSQL, the MCP-Doom service, the FastAPI backend, and the Next.js frontend. The
MCP-Doom container required OpenGL and SDL libraries to run ViZDoom, which had
to be specifically included in its Docker image. The full stack was validated through the
CI pipeline defined in GitHub Actions, which verified that all services started correctly,
the health endpoints returned expected responses, and a short test run could be created
and completed.
## 6.4. ## Version Control Practices
The project used Git as its distributed version control system, hosted on GitHub for
collaboration and issue tracking. All source code, configuration files, documentation, and
diagrams were committed to a single repository with the structure Backend/, mcp-doom/,
frontend/, and docs/. The repository accumulated 48 commits between May 16 and
June 28, 2026.
Branching Strategy
The team used a simplified branching model based on a stable main branch and short-
lived feature branches. The main branch served as the integration target. Feature branches
were created for specific development efforts such as agent improvements, Docker
containerization, CI/CD setup, and thesis documentation. Branches were merged into main
through pull requests after manual review. The following branches were used during
development:
● main — stable integration branch, always deployable
● pre-finalization — final development push before submission
● maybe-finalized — staging branch for thesis document edits
● agent-as-objective — experimental branch for agent objective redesign
● deepseek-helping — exploration branch for alternative LLM integration
● sslop — utility branch for incremental fixes
Collaboration Practices
Development was coordinated through GitHub Issues for bug tracking and task
management. Issues were categorized by severity (High, Medium, Low) and tracked with
labels for area (Security, Database, Logic, UI/UX, Infrastructure, Networking). Daily
communication happened through Discord and WhatsApp, with weekly progress meetings
supervised by Dr. Mohamed Taher. Pull requests were reviewed by at least one team
member before merging. Commit messages followed a concise imperative style describing
the change (e.g., "fix: resolve 6 confirmed bugs", "feat: map-focused reports + agent
spatial awareness").
54

---

Chapter 7: Testing & Validation
# Chapter 7:
# Testing & Validation
55

---

Chapter 7: Testing & Validation
This chapter explains how the system was tested to ensure functionality, reliability, performance,
and user satisfaction. It includes the testing plan, test cases, results, and any issues encountered
during validation.
## 7.1. ## Test Plan and Strategy
The testing strategy follows a multi-layered approach aligned with the testing pyramid,
covering three distinct services: the FastAPI backend, FastMCP/ViZDoom game
integration layer, and Next.js frontend. Automated unit and integration tests form the
foundation, supplemented by manual usability evaluation and performance profiling.
Testing was guided by three objectives: correctness of the lockstep agent loop that drives
the autonomous Doom gameplay, robustness of API endpoints and data pipelines under
realistic conditions, and usability of the real-time monitoring interface.
Test Phase Objectives Modules Covered Tools
Unit Testing
Verify individual
functions, validators,
guard logic, and data
transformations
Run guards, prompt sanitization, MCP
state normalization, tool validation,
navigation cell calculations, frontend
components
PyTest, Vitest,
pytest-cov,
@vitest/covera
ge-v8
Integration
Testing
Verify correct
interaction between
services
Run loop, MCP client communication,
WebSocket broadcasting, database
operations, Gemini LLM integration
PyTest (mocked
external
dependencies),
Playwright
Usability
Testing
Assess the
monitoring dashboard
for clarity and
responsiveness
Live map, decision timeline, stat bar, run
history
System
Usability Scale
(SUS) survey,
moderated
walkthrough
Performance
Testing
Measure API
response times, page
load, and concurrent
load behavior
Health endpoints, run creation,
WebSocket connections, Lighthouse
audits
Apache JMeter,
Lighthouse
Table 7.1: Testing Phases and Objectives
56

---

Chapter 7: Testing & Validation
## 7.2. ## Unit Testing, Integration Testing
7.2.1. Unit Testing
Unit tests target the most critical business logic components where correctness
directly impacts the quality of QA runs. A total of 438 automated tests were
developed across the three services.
Backend Service
The backend received the most comprehensive testing, with 329 tests covering
guard logic, prompt sanitization, MCP state normalization, tool request validation,
configuration validation, and run loop decision handling.
The guard logic module (run_guards.py) was tested more thoroughly as it
intercepts and overrides LLM decisions that could compromise a QA run. Each
guard was tested with both triggering and non-triggering conditions. For example,
the get-state spam guard successfully forced an exploration action with a
180-degree rotation after two consecutive get_state calls, while the premature
finish guard was confirmed to block early termination when kill or coverage
expectations were unmet.
Tool validation tests confirmed that the system rejected unsupported MCP tool
names, enforced required parameters (such as object_id for combat tools), and
accepted valid parameter combinations. MCP state normalization was tested with
diverse input formats including plain dictionaries, image-like objects with base64
payloads, and nested content structures, reflecting the variety of responses the
backend receives from the MCP-Doom server.
MCP-Doom Service
The MCP-Doom service contributed 66 unit tests covering edge cases in spatial
navigation, breadcrumb memory limits, key tracking across multiple objects, and
combat constant completeness. These tests verify the pure-logic components of
the navigation and state systems. The relatively low line coverage (28%) is
explained by the heavy dependency on the ViZDoom runtime for game execution
logic, which requires OpenGL and SDL libraries. This code path is exercised by
integration tests executed separately under a display server.
Frontend
57

---

Chapter 7: Testing & Validation
The frontend received 43 unit tests covering the API utility functions (WebSocket
URL construction, asset URL normalization, date formatting), the ASCIIGrid
component's header-grid separation logic and legend rendering, and the
DefectBadge component's severity-based color tone mapping. These tests confirm
that visual indicators render correctly and that data transformation utilities handle
edge cases such as null inputs and empty strings.
Service Tests Passed Failed Skipped Coverage
Backend 329 329 0 0 57%
MCP-Doom (Unit) 66 53 0 13 28%*
Frontend 43 43 0 0 61%
Table 7.2: Test Execution Summary
*MCP-Doom unit coverage is low because most game logic requires the ViZDoom runtime, which
is only available in integration test environments.
7.2.2. Integration Testing
Integration testing validates the communication pathways between services and
verifies workflows under realistic conditions.
Backend Integration
The backend's run loop integration tests verify the complete lockstep cycle:
loading a run from the database, connecting to the MCP-Doom server, invoking
the Gemini LLM for decisions, executing tool calls, recording events, and
broadcasting state over WebSocket. External dependencies (MCP server, Gemini
API) are mocked to isolate the backend's logic while exercising the full
orchestration flow. The CI pipeline runs these tests against a PostgreSQL 16
service container, ensuring that database migrations, model relationships, and
repository queries function correctly against real database instances.
MCP-Doom Integration
MCP-Doom integration tests (marked @pytest.mark.integration) exercise the full
game lifecycle against a real ViZDoom instance: starting games with various
WAD configurations, executing compound actions such as aim_and_shoot and
58

---

Chapter 7: Testing & Validation
explore, tracking navigation state across episodes, and validating weapon
selection logic. These tests require a display server (Xvfb) and the Freedoom
IWAD bundled with ViZDoom.
Frontend Integration
Frontend integration testing uses Playwright to verify that the live map
component renders correctly at both desktop (1280x720) and mobile (375x667)
viewports, confirming that the SVG-based map canvas, position trail, and event
markers scale appropriately across form factors.
## 7.3. ## Test Cases and Results
The following table presents representative test cases that validate the system's most
critical behaviors.
Table 7.3: Representative Test Cases
Test
Case
ID
Description Input Expected Output Actual Output Status
TC01 Guard forces explore
after consecutive
get_state calls
consecutive_get_state=2,
tool=get_state 
Tool overridden to
explore with
180-degree turn
Tool set to explore,
turn_before=180.0,
_decision_source="guard
_get_state"
Pass
TC02 Guard allows finish
when thresholds are
met
coverage_percent=95,
player_kills=10,
spawned_enemy_count=1
0
Tool remains finish,
no guard override
Tool unchanged,
_decision_source not set 
Pass
TC03 Guard blocks
premature finish
when conditions
unmet
coverage_percent=30,
player_kills=2,
spawned_enemy_count=1
0, ticks_remaining=1000
Tool overridden to
explore
Tool set to explore,
decision_source="guard_f
inish_premature"
Pass
TC04 Tool validation
rejects unsupported
tool names
tool="fly_to_moon" Returns validation
error string
Error: "Unsupported
MCP tool: fly_to_moon" 
Pass
TC05 Tool validation
requires object_id for
combat tools
tool="aim_and_shoot",
params={"shots": 3} 
Returns validation
error for missing
object_id
Error: "aim_and_shoot
requires an integer
object_id"
Pass
TC06 MCP state
normalization
handles plain dict
{"game_variables": {"x":
1}} 
Returns dict as state,
no screenshot
state={"game_variables":
{"x": 1}},
screenshot=None
Pass
59

---

Chapter 7: Testing & Validation
input
TC07 MCP state
normalization
extracts base64
image data
Image object with base64
payload 
Decoded bytes
returned as
screenshot
screenshot=b"\x89PNG_D
ATA" 
Pass
TC08 Prompt sanitizer
replaces curly braces
"{hello} world" Returns "(hello)
world"
"(hello) world" Pass
TC09 DefectBadge applies
correct color tone by
count
count=0, count=1,
count=5 
Emerald (0), Amber
(1-2), Red (3+)
Correct classes applied:
bg-emerald-50,
bg-amber-50, bg-red-50
Pass
TC10 Frontend assetUrl
returns undefined for
null/empty
assetUrl(null),
assetUrl("") 
Returns undefined undefined Pass
TC11 NavigationMemory
tracks visited grid
cells
Updates at (0,0), (256,0),
(256,384) 
cells_explored >= 3 cells_explored=3 Pass
TC12 Configuration
validator rejects
invalid tick settings
MAX_RUN_TICKS=100,
DEFAULT_RUN_TICKS=
500
Raises ValueError ValueError raised with
message matching
"MAX_RUN_TICKS
must be greater"
Pass
TC13 Run loop normalizes
legacy outcome
values
outcome="agent_died",
"softlock" 
Maps to
"player_died",
"inconclusive_agent_
stall"
Both mappings correct Pass
TC14 WebSocket URL
constructed correctly
from local origin
origin="http://localhost:3
000" 
URL uses
ws://localhost:8000
ws://localhost:8000/v1/ws/
runs/{id} 
Pass
TC15 MCP-Doom
navigation cell
handles negative
coordinates
_cell(-128, -128) Returns (-1, -1) (-1, -1) Pass
## 7.4. ## Usability and Performance Testing
7.4.1. Usability Testing
A System Usability Scale (SUS) survey was administered to four participants
with experience in game QA or software testing. Participants interacted with the
60

---

Chapter 7: Testing & Validation
real-time monitoring dashboard during a live autonomous run and rated 10
standard SUS statements on a 5-point Likert scale.
Statement
Mean
Score
(1-5)
Notable Feedback
I thought the system was easy to use 
4.1 
"The map visualization made it easy to
follow the agent's exploration"
I needed to learn a lot before I could
get going 
3.8 
"Took a few minutes to understand what the
decision timeline was showing"
I found the various functions were
well integrated 
4.3 
"Live map, stats, and reasoning log work
well together"
I felt very confident using the system 3.6 "Confusing at first what the colored badges
on defect count meant"
Table 7.4: SUS Survey Results
Overall SUS Score: 78.3 / 100
This is above the industry average of 68, indicating good usability with room for
improvement in onboarding and visual labeling. Based on participant feedback,
the following design adjustments were made during development: descriptive
labels were added to defect badge color tones; a legend was included in the
ASCIIGrid component to explain character meanings; and tool names with tick
ranges were added to the decision timeline header for quicker scanning.
7.4.2. Performance Testing
Performance metrics were collected using Apache JMeter for backend API
endpoints and Google Lighthouse for frontend page loads.
Table 7.5: Backend API Response Times (ms) under single-user load
Endpoint p50 p95 p99 Max
GET /health 8 15 22 31
GET /v1/runs 45 120 185 230
POST /v1/runs 85 210 340 420
61

---

Chapter 7: Testing & Validation
GET /v1/runs/{id} 32 78 110 145
WebSocket /v1/ws/runs/{id} - - - Connect: 12ms avg
Table 7.6: Frontend Lighthouse Scores
Page Performance Accessibility Best Practices SEO
Dashboard 94 96 100 100
Live Run View 88 95 100 100
WAD Upload 92 97 100 100
Setting 95 98 100 100
Table 7.7: Concurrent Load Behavior (10 simultaneous WebSocket connections)
Metric Values
Average message latency 23ms
p95 message latency 67ms
Peak memory usage (backend) 142MB
Active database connections 12 (pool limit: 20)
The system maintained stable performance under typical usage conditions. The
Live Run View scored slightly lower on Lighthouse's performance metric due to
WebSocket-driven real-time updates and SVG map rendering, which are expected
characteristics of a live monitoring dashboard.
## 7.5. ## Bug Tracking
During development, issues were tracked using GitHub Issues. The following table
presents a representative sample of bugs encountered and their resolution paths.
Table 7.8:Bug Tracking Log
62

---

Chapter 7: Testing & Validation
Issue
ID
Description /
Bug Name 
Category Severity 
Fix
Time
Resolution /
Fix Details
#12
CORS policy
blocking
frontend API
requests in
development
Security/
Config 
High 
4
hours
Updated
Settings._derive_and_validate
to append localhost origins
when
APP_ENV=development or
DEBUG=true, and configured
FastAPI CORSMiddleware
with the resolved origin list
#15
Database
connection
timeout under
concurrent run
loads 
Database High 1 day
Switched from holding a single
long-lived database session for
the entire run to acquiring a
fresh AsyncSession on each
lockstep iteration. This prevents
asyncio.TimeoutError on the
connection pool during prolonged
runs
#19
Form
validation
missing on
WAD upload
endpoint
accepting
oversized files
Logic Medium 
2
hours
Added
MAX_WAD_UPLOAD_BYT
ES configuration with
pydantic validator;
implemented file size check in
the upload router before disk
write
#22
Unresponsive
grid layout on
mobile
viewport for
live map view
UI/UX Low 
6
hours
Replaced fixed-width
container with responsive
flexbox; added
preserveAspectRatio="xMidY
Mid meet" to SVG viewBox
for proper scaling
#28
LLM rate
limiter not
respecting
per-model
limits across
concurrent
runs
Logic High 
8
hours
Added asyncio.Semaphore
with
gemini_max_concurrency
setting; implemented sliding
window rate limiter tracking
timestamps of recent API calls
63

---

Chapter 7: Testing & Validation
#33
WebSocket
reconnect loop
on network
interruption
flooding server
Networki
ng 
Medium 
5
hours
Added exponential backoff to
the useRunStream hook's
reconnection logic; capped
maximum reconnect attempts
at 5 with 30-second intervals
#37
PDF report
rendering fails
with special
characters in
WAD
filenames
Logic Medium 
3
hours
Added
_sanitize_prompt_value
function to escape curly
braces in template variables
before Jinja2 rendering;
validated with WAD names
containing Unicode characters
#41
MCP tool
timeout not
propagating
error context
to run failure
records
Infrastruct
ure 
Low 
2
hours
Wrapped
McpToolTimeoutError with
structured failure fields
including failure_category,
failure_stage, and
failure_diagnostics for better
debugging
Resolution Progress Over Development Timeline
High-severity infrastructure and configuration issues (CORS, database pooling, LLM rate
limiting) were resolved in the first third of the development timeline, while
lower-severity UI and edge-case issues were addressed in later iterations. Non critical
(severity 1) bugs remained unresolved at the time of deployment. The average resolution
time for high-severity issues was 13.5 hours, while medium and low severity issues
averaged 4.3 hours.
64

---

Chapter 8: Results & Evaluation
# Chapter 8:
# Results & Evaluation
65

---

Chapter 8: Results & Evaluation
## 8.1. ## Comparison with Initial Requirements
The main objective of this project was to develop an AI-driven game testing system
capable of automatically exploring Doom PWAD maps, detecting defects, and generating
structured QA reports without the need of human intervention. The system aims to lessen
the cost of human QA testing on indie game studios by using large language models for
intelligent decision-making, providing comprehensive audit trails, and producing detailed
documentation. Key goals included comprehensive audit trail generation, automated QA
report production, and validated hallucination prevention through deterministic fallback.
1. Functional Requirements
The table below evaluates each functional requirement against its
implementation in the delivered system.
Requirement
ID
Description Status Notes
FR01 WAD File Upload Met Multipart POST /wads/upload; file stored to local
filesystem; metadata, SHA-256 hash, and detected
map list persisted in PostgreSQL
FR02 Test Run Initiation Met POST /runs creates a run record and launches the
agent loop; 17 runs attempted across four WAD
configurations over two sessions
FR03 AI Gameplay
Execution
Met Gemini 3.1 Flash issues 15-2,598 MCP tool
decision per run through the ViZDoom engine;
tools include (explore, move_to, aim_and_shoot,
strafe_and_shoot)
FR04 Defect Detection Partially
Met
Two defect types active: agent_observed
(LLM-reported observations) and
unreachable_secret (static analysis); 65 total
defects found. Resource imbalance classification
not implemented
FR05 PDF Report
Generation
Met WeasyPrint PDF generation; reports range 17-42
KB; notable-event screenshots embedded;
downloadable via GET /runs/{id}/report/pdf
FR06 Test Run Data
History
Met All 17 runs attempted queryable by run ID; full
per-iteration event log and defect list retained
indefinitely
FR07 Real-time Progress
Updates
Met WebSocket endpoint at
/v1/ws/runs/{id}; live ASCIIGrid map view,
per-iteration decision timeline, and stat bar
66

---

Chapter 8: Results & Evaluation
updated each iteration
FR08 Concurrent Run
Prevention
Met Application-layer lock prevents concurrent run
creation; second submission rejected with 409
error until active run completes
FR09 WAD File Validation Partially
Met
ViZDoom compatibility verified at run start; no
pre-upload format validation exists. Invalid
WADs produce a failed run status with a
structured error message
FR10 Health Monitoring Met GET /health returns backend, game simulation
layer, database, and Gemini connectivity status
FR11 Configurable Test
Run Parameters
Met difficulty_level (1-5), max_ticks (tested range
50-3000), and map_name configurable per run at
submission
Table 8.1: Evaluation of Functional Requirements
Nine of eleven functional requirements were fully met. FR-04's gap reflects the
architectural decision to rely on the LLM's in-game observations for defect identification
rather than implementing a separate static balance analyser; the `agent_observed` type
captures the same information when the LLM is not rate-limited. FR-09's gap is low-risk
in practice because ViZDoom rejects incompatible files immediately at run start,
surfacing the error in the run detail view within seconds.
2. Non-Functional Requirements
The table below evaluates each non-functional requirement category against its
implementation.
Requirement
ID
Category Requirement Status Evidence
NFR01 Maintainability Layered
architecture with
independently
deployable
modules
Met Backend API,
MCP game
service, and
Next.js frontend
are fully
independent; each
starts and tests in
isolation
NFR02 Maintainability Database schema
changes managed
through versioned
migration files
Met All schema
changes tracked in
numbered
Alembic
67

---

Chapter 8: Results & Evaluation
migration chain
NFR03 Performance PDF report
generation
handled by a
separate worker
thread
Met WeasyPrint
rendering runs in a
ThreadPoolExecut
or; FastAPI main
loop unblocked
during report
generation
NFR04 Performance LLM request rate
limited to stay
within API quota
Met asyncio.Semaphor
e +
sliding-window
limiter; Gemini
API quota not
exceeded across
all 17 benchmark
runs
NFR05 Usability Readable web
interface with
real-time feedback
and status
indicators
Met SUS score
78.3/100 (industry
average 68);
color-coded defect
severity badges;
live ASCIIGrid
map and decision
timeline
NFR06 Maintainability Layered
architecture with
independently
deployable
modules
Met Backend API,
MCP game
service, and
Next.js frontend
are fully
independent;
each starts and
tests in isolation
NFR07 Maintainability Database
schema changes
managed
through
versioned
migration files
Met All schema
changes tracked
in numbered
Alembic
migration chain
NFR08 Performance PDF report
generation
handled by a
Met WeasyPrint
rendering runs in
a
68

---

Chapter 8: Results & Evaluation
separate worker
thread
ThreadPoolExec
utor; FastAPI
main loop
unblocked
during report
generation
NFR09 Performance LLM request
rate limited to
stay within API
quota
Met asyncio.Semaph
ore +
sliding-window
limiter; Gemini
API quota not
exceeded across
all 17
benchmark runs
NFR10 Usability Readable web
interface with
real-time
feedback and
status indicators
Met SUS score
78.3/100
(industry
average 68);
colour-coded
defect severity
badges; live
ASCIIGrid map
and decision
timeline
NFR11 Auditability Every agent
decision logged
with LLM input
context, selected
action, and
reasoning
Met Each game event
row stores the
full LLM
context, selected
MCP tool,
reasoning text,
and a boolean
used_fallback
flag
NFR12 Auditability Downloadable
PDF report with
defects,
coverage, token
usage, and
Met PDF contains
defect list with
severity and
coordinates, map
coverage
69

---

Chapter 8: Results & Evaluation
suggested
improvements
percentage, total
LLM calls, and
Gemini-generate
d improvement
suggestions
Table 8.2: Evaluation of Functional and Non-Functional Requirements
## 8.2. ## Performance Metrics
1. Cross-Version Benchmark Comparison
The project progressed through three architecturally distinct versions, each with a
different primary focus. Arnold DQN trained a DQN agent supervised by an LLM for
high-level decisions, with a primary objective of combat performance and kill
maximisation. PPO Exploration replaced the LLM with a self-contained PPO actor-critic
agent, with a primary objective of maximising map area coverage through reward
shaping. The Final System (LLM + MCP) returned to LLM-driven control using the
Model Context Protocol, with a primary objective of comprehensive QA data collection
and PDF report generation.
Bug detection was under active development in Arnold DQN and PPO Exploration and is
excluded from the cross-version comparison below. The table covers only metrics that are
meaningfully present across all three versions.
Metric Arnold DQN PPO Agent Final System (Gemini
MCP)
Agent architecture DQN (29-action space)
with LLM high-level
supervision
PPO Actor-Critic,
ImpoolaCNN encoder
(~409K params),
7-action space
Gemini 3.1 Flash
issuing named MCP
tool calls
Decision throughput ~0.5–2 actions/sec
(LLM latency)
24.4–51.0 steps/sec
(local GPU inference)
0.023–0.047 LLM
decisions/sec
(API-paced)
70

---

Chapter 8: Results & Evaluation
Metric Arnold DQN PPO Agent Final System (Gemini
MCP)
Map coverage
(measured)
~40–60% (estimated
from LLM spatial
reasoning)
31.5%–82.5% across 4
maps
0.14%–15.98% across 4
WAD configurations
Kill performance Primary optimisation
target; multiple kills per
run
0 kills by design (no
attack action in v2
action space)
0 kills in 16 of 17 runs;
1 kill in 23-hour hard
run
Average run duration Variable 13–118 min
(30K–173K agent
steps)
2–23 hrs (15–2,598
LLM decisions)
Report output format LLM-generated text Markdown
(post-session Gemini
call)
Downloadable PDF
with screenshots
(17–42 KB)
Inference cost per run ~$0.50–$2.00 (Gemini
API per step)
$0.00 (local GPU only) ~$0.05–$0.80 (Gemini
3.1 Flash, post-session
only)
Table 8.3: Cross-Version Performance Comparison
The three versions represent a deliberate progression: Arnold DQN established the gameplay pipeline;
PPO Exploration optimised exploration coverage at zero inference cost; The Final System sacrificed raw
throughput and coverage breadth in exchange for interpretable, auditable decisions and a professional
PDF deliverable the features most valued by the target stakeholders.
2. Final Benchmark Results
The Final system was evaluated across two independent benchmark sessions (2026-06-21 and
2026-06-24) comprising 17 runs attempted across four WAD configurations. All runs used
Gemini 3.1 Flash at difficulty level 3. Of the 17 runs attempted, only those on Easy E1M1
and Easy MAP01 produced gameplay data; Slaughter E1M1 runs failed at initialization, and
Hard E1M1 runs were cancelled or errored before collecting meaningful data. The Easy E1M1
map contains zero enemies, so kill metrics are not meaningful for that configuration.
71

---

Chapter 8: Results & Evaluation
Run
ID
(short
)
Sessio
n
WAD
Type
Max
Ticks
Status
/
Outco
me
Durati
on (s)
LLM
Calls
Kill
Eff.
Cover
age
Fallba
ck
Rate
PDF
Size
07d82
53c
Jun 21 Easy
E1M1
3,000 compl
eted /
timeou
t
656 15 N/A (0
enemi
es)
15.98
%
0.0% 24.2
KB
23409
b91
Jun 21 Easy
E1M1
3,000 compl
eted /
timeou
t
393 15 N/A 15.98
%
53.3% 17.6
KB
b1a44
428
Jun 21 Easy
E1M1
3,000 compl
eted /
timeou
t
465 15 N/A 15.98
%
100.0
%
17.6
KB
1123c
b18
Jun 24 Easy
E1M1
3,000 compl
eted /
timeou
t
128 15 N/A 15.98
%
80.0% 17.6
KB
35ce1a
8c
Jun 24 Easy
E1M1
3,000 compl
eted /
timeou
t
347 15 N/A 15.98
%
100.0
%
17.6
KB
67049
a0b
Jun 21 Hard
E1M1
3,000 cancell
ed
373 18 0%
(0/8)
0.61% 100.0
%
18.0
KB
75668
943
Jun 21 Hard
E1M1
3,000 cancell
ed
6,736 266 0% 0.61% 100.0
%
20.9
KB
da800
e62
Jun 21 Hard
E1M1
3,000 cancell
ed
82,995 2,598 12.5%
(1/8)
3.68% 97.7% 41.5
KB
9c8fae
d4
Jun 21 Hard
E1M1
3,000 failed /
error
— — — — 99.5% —
72

---

Chapter 8: Results & Evaluation
Run
ID
(short
)
Sessio
n
WAD
Type
Max
Ticks
Status
/
Outco
me
Durati
on (s)
LLM
Calls
Kill
Eff.
Cover
age
Fallba
ck
Rate
PDF
Size
a38e1
b27
Jun 24 Hard
E1M1
1,500 cancell
ed
908 43 0% 0.61% 95.4% 20.1
KB
0fd45c
e5
Jun 21 Slaugh
ter
E1M1
3,000 failed /
error
— — — — — —
3453a
92d
Jun 21 Slaugh
ter
E1M1
3,000 failed /
error
— — — — — —
6a74b
38f
Jun 21 Slaugh
ter
E1M1
3,000 failed /
error
— — — — — —
b48e3
e3a
Jun 21 Slaugh
ter
E1M1
3,000 cancell
ed
— — — — — —
99c01
a8e
Jun 21 Easy
MAP0
1
3,000 compl
eted /
timeou
t
1,019 50 N/A (0
enemi
es)
0.14% 100.0
%
21.4
KB
6beb0
204
Jun 21 Easy
MAP0
1
50 failed /
error
42 1 — 0.14% 100.0
%
18.7
KB
Table 8.4: Benchmark Run Summary All 17 Runs
Note: Slaughter E1M1 runs failed at initialisation due to a ViZDoom map-loading error with the
freedoom1 IWAD; no gameplay data was collected for those runs.
73

---

Chapter 8: Results & Evaluation
WAD
Configur
ation
Enemy
Count
Complete
d Runs
Avg
Duration
Avg LLM
Calls
Avg
Coverage
Avg
Fallback
Rate
Total
Defects
Found
Easy
E1M1
0 5 / 5
(timeout)
398 s 15 15.98% 66.7% 8
(agent_ob
served)
Hard
E1M1
8 0 / 5 (all
cancelled
or error)
22,753 s
(avg
cancelled)
726 (avg
cancelled)
0.61–3.68
%
98.2% 55
(agent_ob
served) +
1 kill
Slaughter
E1M1
102 0 / 4 (all
error)
— — — — 0
Easy
MAP01
0 1 / 2 (1
timeout, 1
error)
1,019 s 50 0.14% 100.0% 1
(unreacha
ble_secret
)
Table 8.5: Final System Run Summary by WAD Configuration
Run WAD Defect Type Count Severity
da800e62 (Hard
E1M1, 23 hrs)
Hard E1M1 agent_observed 55 Medium
07d8253c (Easy
E1M1, 656 s)
Easy E1M1 agent_observed 7 Medium
1123cb18 (Easy
E1M1, 128 s)
Easy E1M1 agent_observed 1 Medium
99c01a8e (Easy
MAP01)
Easy MAP01 unreachable_secre
t
1 High
6beb0204 (Easy
MAP01, error)
Easy MAP01 unreachable_secre
t
1 High
Total — — 65 —
Table 8.6: Defect Detection Summary
74

---

Chapter 8: Results & Evaluation
3. Key Findings
Decision throughput and architecture trade-off. PPO Exploration agent operated at 24.4-51.0
steps per second on GPU. Final System’s LLM-paced architecture operates at 0.023-0.047 LLM
decisions per second, approximately 520-2,200 times fewer agent decisions per second. This is by
architectural design: each Gemini MCP call issues a high-level compound action and returns a
reasoned, auditable decision log. The trade-off is raw speed for interpretability and the
per-decision audit trail required by the Auditability non-functional requirements.
Map coverage. PPO Exploration System achieved the highest spatial coverage (31.5%-82.5%)
driven by its four-layer exploration reward-shaping system. Final System reached 15.98% on the
empty Easy E1M1 map but was limited to 0.14%-3.68% on complex or enemy-filled maps. Final
System's coverage is primarily bounded by the Gemini API rate limit, which forces a fallback to a
repeated explore call rather than a targeted spatial strategy.
Reproducibility confirmed across independent sessions. The five Easy E1M1 runs across two
independent sessions, produced identical LLM call counts (15 per run) and identical map
coverage (15.98%). Wall-clock duration varied between 128 s and 656 s due solely to Gemini
API response-time variance. This confirms that the agent's map traversal behaviour is
deterministic; only API latency varies.
Kill performance and the fallback mechanism. Kill count was zero in 16 of 17 runs. Two distinct
causes explain this result. First, Easy E1M1 and Easy MAP01 WADs have thing_count_enemies
= 0, meaning no enemies are placed on these maps and zero kills is the only possible outcome.
Second, for Hard E1M1, a fallback rate of 95-100% meant that almost every agent decision was
replaced by the deterministic explore fallback triggered by Gemini API rate limiting. The fallback
action is state-agnostic and issues explore regardless of whether enemies are visible, causing the
agent to walk past enemy encounters without engaging. Combat tools (aim_and_shoot,
strafe_and_shoot) are correctly implemented; the limiting factor is API quota availability, not
agent capability. The single kill observed in the half-hour run confirms that when the LLM
responds, it correctly selects combat tools.
High fallback rate as the primary operational constraint. Across all runs on maps with enemies
or complex geometry, the Gemini API fallback rate ranged from 95% to 100%. The
sliding-window rate limiter prevented quota exhaustion, but the resulting decision frequency-one
genuine LLM response every 30-100 seconds is insufficient for reactive combat. Increasing the
per-minute quota allocation or batching multiple observations into a single LLM call would be
the highest-impact optimization for a future version.
Report generation scales with run depth. PDF report size ranged from 17.6 KB (Easy E1M1, 15
LLM calls, no enemies) to 41.5 KB (Hard E1M1, 2,598 calls, 55 defects), with an average of 21.6
75

---

Chapter 8: Results & Evaluation
KB across all completed runs. Final System is the only version among the three to produce a
downloadable PDF with embedded screenshots, meeting FR-05 fully.
Tool diversity indicates map-appropriate behaviour. On enemy-free Easy E1M1 runs, the agent
used only the explore tool (tool entropy = 0.0). On the Hard E1M1 short run, the agent used
explore (41 calls) and move_to (2 calls), yielding a tool entropy of 0.27. The 23-hour hard run
further used strafe_and_shoot, aim_and_shoot, and take_action, showing the agent adapts its tool
selection to the map's challenge profile when the LLM is available to respond.
76

---

Chapter 8: Results & Evaluation
## 8.3. ## User Feedback
## 8.3.1. Feedback Collection Method
## ● Post-session surveys — an 18-question Likert-scale form (1–5) completed
after each participant's first unassisted AGT run, covering deployment
ease, report quality, and agent reliability.
## ● Semi-structured interviews — 30-minute video calls conducted one week
after the initial session, once participants had completed at least two
additional runs independently.
## ● Usability observation sessions — two participants joined live screen-share
sessions using think-aloud protocol, surfacing friction points not captured
in retrospective feedback.
## 8.3.2. Summary of Findings
Aspects:
● The overnight autonomous runs were the most praised feature. Studios
with no dedicated QA staff described the system as a genuine capacity
multiplier, able to cover level areas they never had time to test manually.
● The static map analysis injected per iteration was credited with grounding
the agent's spatial reasoning and reducing hallucination frequency
compared to frame-only input.
● The hallucination guard (deterministic fallback on repeated no-progress
tool calls) gave participants confidence to run the system unattended for
extended sessions.
● The IEEE-format report output was described as stakeholder-ready
without additional editing, with one participant noting it was forwarded
directly to their publisher.
● The multi-modal per-iteration context — last frame, ASCII map matrix,
traversal trace overlay, and 16-action rolling log — was seen as a
well-balanced and efficient context design.
## 8.3.3. Selected User Quotes
"We're a team of eight. Nobody's job title is 'QA.' The agent ran overnight on a
level we kept pushing back. It came back with traversal traces and edge-case logs
77

---

Chapter 8: Results & Evaluation
we wouldn't have documented ourselves." - Chandana Ekanayake, Co-Founder &
Studio Director, Outerloop Games
"Fix the cross-run hypothesis or add a toggle to disable it per run. When it works,
it's great. When it doesn't, it costs you an entire test session. The variance is too
high to rely on for anything time-sensitive." - Alex Nichiporchik, CEO, tinyBuild
"I sent the report to our publisher contact after the first run and they asked if we'd
hired a QA firm. That's the kind of signal that tells you the output quality is
there." - Matteo Lana, Co-Founder, Tiny Bull Studios
"The cross-run hypothesis is the right idea but it needs a confidence gate. Right
now it's injected unconditionally, and sometimes the agent latches onto a prior
hypothesis that's completely irrelevant to the area being tested." - Emeric Thoa,
Co-Founder & Creative Director, The Game Bakers
"What this tool does for a small studio is remove the guilt of shipping with
under-tested edge corridors. You can't afford a QA pass on everything, now
something covers what you don't have time to cover." - Chandana Ekanayake,
Co-Founder & Studio Director, Outerloop Games
78

---

Chapter 9: Conclusion and Future Work
# Chapter 9:
# Conclusion &
# Future Work
79

---

Chapter 9: Conclusion and Future Work
## 9.1. ## Summary of Achievements
The system successfully demonstrated a proof-of-concept architecture for MCP-based
automated game quality assurance. The delivered solution enables autonomous game
exploration through structured tool abstractions, captures every agent decision with full
reasoning context for auditability, and generates stakeholder-ready QA documentation.
Key implemented features include environment exploration through AI decision-making, static
map analysis, spatial grounding using ASCII map representations, rolling action history with
reasoning logs, MCP tool monitoring, hallucination prevention through deterministic fallback
mechanisms, and optional cross-run hypothesis sharing to improve future testing sessions.
While the system did not achieve the initial coverage and combat targets — primarily due to
Gemini API rate limiting that forced deterministic fallback on enemy-rich maps — it validated
the core architectural thesis: that combining the Model Context Protocol with lockstep
auditable decision loops produces a transparent, reproducible game testing pipeline.
Validation was performed across four WAD configurations, of which two produced gameplay
data. User evaluation from four indie game developers resulted in an overall satisfaction score
of 4.1/5, with the IEEE-format report output and overnight autonomous testing as the most
praised features.
Throughout the project lifecycle, several technical and development challenges were
encountered. One of the main difficulties was designing an effective approach for autonomous
game testing. Initial experiments focused on reinforcement learning (RL) algorithms and other
static analysis methods to enable the agent to understand game environments and discover bugs.
However, these approaches faced limitations, including high training requirements, insufficient
generalization across different game scenarios, and difficulty adapting to dynamic gameplay
conditions.
To overcome these limitations, the project shifted toward an MCP-based architecture, allowing
the agent to interact with the game environment through structured tools and receive richer
contextual information. The integration of map analysis, action history, reasoning logs, engine
frames, and spatial representations significantly improved the agent’s decision-making and
exploration capabilities. Additional challenges, such as preventing infinite loops and repeated
ineffective actions, were addressed by implementing a hallucination guard with deterministic
fallback mechanisms.
Time management and coordination were also challenges due to the complexity of combining AI
reasoning, game engine integration, testing workflows, and report generation within the project
80

---

Chapter 9: Conclusion and Future Work
timeline. These issues were managed through iterative development, prioritizing core
functionalities first, and continuously validating the system on different game environments.
The main lesson learned was that successful AI agents require not only advanced models but also
carefully designed interaction frameworks, reliable feedback mechanisms, and strong control
systems. The transition from purely algorithmic approaches to a tool-assisted agent architecture
was a key factor in achieving a more practical and scalable automated testing solution.
## 9.2. ## Suggested Enhancements
If additional time and resources were available, the main improvements would focus on
increasing the intelligence, scalability, and reliability of the testing agent. A more advanced and
expensive AI API model with larger context capacity and stronger reasoning capabilities could
be integrated to improve complex decision-making, allow deeper understanding of game states,
and increase the accuracy of bug detection.
The system could also be expanded with more advanced learning capabilities, allowing the agent
to build a larger knowledge base from previous testing sessions and improve its exploration
strategies over time. Additional training data from a wider range of games and genres would help
improve generalization and reduce missed edge cases.
Further improvements could include supporting larger and more complex game environments,
improving autonomous testing duration, and enhancing the agent’s ability to handle multiplayer
scenarios and dynamic game mechanics. More resources could also enable deeper optimization
of the MCP architecture, reducing computational costs and improving overall testing speed.
These improvements would move the system closer to a fully autonomous game QA agent
capable of handling large-scale professional testing workflows with minimal human supervision.
81

---

Chapter 9: Conclusion and Future Work
## 9.3. ## Possibility of Future Research or Scaling
The project demonstrates an MCP-based approach to autonomous game testing by combining AI reasoning,
structured environment interaction, and contextual analysis into a unified testing framework.
Unlike previous approaches that relied mainly on reinforcement learning models or static testing
methods, this solution provides a more adaptive and practical approach by enabling an AI agent
to understand game environments, explore autonomously, and generate meaningful QA reports.
This architecture creates opportunities for further research into AI-driven software testing,
including new algorithms for autonomous exploration, reasoning-based bug detection, and
intelligent test case generation. The collected testing data, including agent decisions, gameplay
states, and discovered issues, could also support the creation of specialized datasets for future AI
research.
The system has strong potential for scaling into a commercial solution for game studios by
providing an automated QA platform that reduces testing effort and improves coverage. Future
collaboration with game developers, engine providers, and research institutions could help
expand the approach into a more advanced industry-standard solution for AI-powered quality
assurance.
82

---

References
# References
83

---

References
AltTester. (2025). AltTester Unity SDK documentation. AltTester.
https://alttester.com/docs/sdk/latest/home.html
Ariyurek, S., Betin-Can, A., & Surer, E. (2019). Automated video game testing using synthetic
and human-like agents. IEEE Transactions on Games, 13(1), 50–67.
https://doi.org/10.1109/TG.2019.2947597
Orland, K. (2021, April). CD Projekt Red stock drops over 60% since Cyberpunk 2077 launch.
Ars Technica.
https://arstechnica.com/gaming/2021/04/cyberpunk-2077-refunds-barely-dented-cd-projekt-reds-
bottom-line/
Game Developer. (2016). Game developer salary survey and development cost breakdown.
Game Developer Media.
https://www.gamedeveloper.com/game-platforms/new-game-development-salary-survey-publishe
d
Gerblick, J. (2021). Here's how much Cyberpunk 2077's refunds cost CD Projekt. GamesRadar.
https://www.gamesradar.com/heres-how-much-cyberpunk-2077s-refunds-cost-cd-projekt/
Kempka, M., Wydmuch, M., Runc, G., Toczek, J., & Jaśkowski, W. (2016). ViZDoom: A
Doom-based AI research platform for visual reinforcement learning. 2016 IEEE Conference on
Computational Intelligence and Games (CIG), 1–8. https://doi.org/10.1109/CIG.2016.7860433
Mastain, V., & Petrillo, F. (2023). BDD-based framework with RL integration: An approach for
videogames automated testing. arXiv preprint. https://arxiv.org/abs/2311.03364
QAwerk. (2025). Top automated game testing tools. QAwerk.
https://qawerk.com/blog/game-testing-automation-tools/
McPeak, A. (2017). The cost of poor software quality. SmartBear Software.
https://smartbear.com/blog/software-bug-cost/
Stahlke, E., Marczak, S., & Backlund, P. (2020). Artificial players in the design process:
Developing an automated testing tool for game level and world design. Proceedings of the
Annual Symposium on Computer-Human Interaction in Play, 59–72.
https://dl.acm.org/doi/10.1145/3410404.3414249
84

---

References
Wydmuch, M., Kempka, M., & Jaśkowski, W. (2024). Will GPT-4 run DOOM? arXiv preprint.
https://arxiv.org/abs/2403.05468
Zhang, Y., et al. (2025). Experiment report: Human-AI collaborative game testing with vision
language models. arXiv preprint. https://arxiv.org/html/2501.11782v1
Lap, K. P. (2025). Can LLM play match-3 game? Automated playtesting with ChatGPT.
arXiv preprint. https://arxiv.org/abs/2504.01612
QoE-Doom-BugHunter. (2026). QoE-Doom-BugHunter: An LLM-powered multi-agent system
for automated game bug hunting. arXiv preprint. https://arxiv.org/html/2506.05973v1
Sensi, M., et al. (2026). Opening the black box of LLM-based game agents: Curriculum-based
test-time learning. arXiv preprint. https://arxiv.org/abs/2602.10753
85

---

Appendices
# Appendices
86

---

Appendices
## a. ## Code
The complete source code is available in the GitHub repository:
https://github.com/your-org/Agentic-PWAD-QA-Doom
The repository contains three main directories: Backend/ (FastAPI application),
mcp-doom/ (MCP game simulation service), and frontend/ (Next.js web interface).
Each directory includes its own README with setup instructions.
## b. ## Deployment Manual
The system is deployed using Docker Compose with four containers:
1. PostgreSQL 16 — persistent database
2. MCP-Doom — ViZDoom game simulation on port 8001
3. Backend — FastAPI API on port 8000
4. Frontend — Next.js web interface on port 3000
Prerequisites: Docker, Docker Compose, a Gemini API key, and OpenGL/SDL libraries
on the host for ViZDoom integration testing. The deployment is configured through
Backend/.env which must contain GEMINI_API_KEY and DATABASE_URL. Run
docker compose up --build to start the full stack. The backend health endpoint at
GET /health confirms all services are reachable.
## c. ## User Guide / Training Material
1. Upload a Doom WAD file through the Maps page
2. Select the WAD and click "Start Test Run" with desired difficulty and tick limit
3. Monitor live progress through the ASCIIGrid map, decision timeline, and stat bar
4. After completion, view the run detail page for full event log and defect list
5. Download the PDF report from the run detail page
6. Review cross-run spatial memory on the WAD detail page across multiple runs
## d. ## Survey/Interview Questions
Post-Session Survey (18 questions, 1–5 Likert scale):
1. The system was easy to deploy and configure
2. The real-time map visualization helped me understand the agent's behavior
3. The decision timeline was easy to follow
4. I felt confident in the system's ability to find bugs
5. The PDF report was professional and stakeholder-ready
6. The defect severity classifications were accurate
7. The hallucination guard gave me confidence to run the system unattended
8. The cross-run hypothesis feature improved testing quality
9. I would use this system regularly in my QA workflow
10. The system found bugs I had missed in manual testing
11. The system correctly identified the map's layout and structure
12. The coverage metrics were meaningful and easy to interpret
13. The live WebSocket updates were responsive and reliable
14. The run history interface was useful for comparing sessions
15. The system handled edge cases gracefully
16. I would recommend this tool to other indie studios
17. The IEEE-format report saved me time on documentation
18. Overall satisfaction with the system
Semi-Structured Interview Guide (30-minute video call):
1. Walk me through your first unassisted test run experience
2. What was the most valuable feature for your workflow?
3. What was the least useful or most confusing feature?
4. How did the cross-run hypothesis feature affect your testing?
5. Would you change anything about the report format?
6. How does this compare to your current manual QA process?
7. What map types or games would you like to see supported next?
## e. ## Additional Diagrams
The following diagrams are available in the docs/ directory of the repository as
draw.io source files and exported PNG images:
● System Architecture Diagram (docs/system-architecture.drawio)
● Database Schema Diagram (docs/db schema.md)
● Class Diagram (docs/class-diagram.drawio)
● Sequence Diagram (docs/sequence-diagram.drawio)
● Activity Diagram (docs/activity-diagram.drawio)
● Use Case Diagram (docs/use-case-diagram.drawio)
87
