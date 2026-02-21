**Esence**

Product Requirements Document

*v0.2 --- Node, Protocol & Memory Edition*

  ------------------ ----------------------------------------------------
  **Product**        Esence Protocol

  **Version**        0.2 --- Node + Memory

  **Status**         Pre-MVP / Architecture Definition

  **Author**         Node 0 --- Genesis Owner

  **Last Updated**   February 2026

  **Changes from     Added: Node Architecture, ANP Protocol Integration,
  v0.1**             Essence Memory Model, Human-Agent Integration Loop
  ------------------ ----------------------------------------------------

*\"You are not sharing your subscription. You are sharing who you
are.\"*

**1. Executive Summary**

Esence is a decentralized, open-source protocol that enables any person
to create a living digital agent that gradually absorbs their identity,
knowledge, and values through interaction. These agents communicate
asynchronously with each other --- and with their human owners ---
forming a peer-to-peer network of human-amplified intelligences.

The network grows organically through personal invitation: each new node
is introduced by an existing one, creating a web of trust rather than a
platform of strangers. There is no central server, no corporate owner,
and no algorithm extracting engagement. The protocol is the product.

Version 0.2 of this PRD deepens the technical foundation: how the node
works, how it communicates via the ANP protocol, and how the essence
memory model captures and evolves a person\'s identity over time.

*\"The internet connected documents. Social networks connected people.
Esence connects intelligences.\"*

**2. Problem Statement**

**2.1 The Knowledge Trap**

Human expertise is structurally inaccessible. Every professional,
specialist, and experienced individual carries knowledge that others
could benefit from --- but time, geography, and cost prevent meaningful
sharing at scale.

Current AI solves a different problem: it provides generic intelligence.
Powerful, but impersonal. It cannot replicate the nuanced judgment of a
specific person who has spent years in a domain.

**2.2 What Is Missing**

-   A way to represent a specific person\'s knowledge in a scalable,
    asynchronous format

-   A trust model grounded in real human identity, not anonymous AI
    output

-   A decentralized infrastructure that no company can own or shut down

-   An organic growth model based on relationships, not viral marketing

-   A memory model that captures essence implicitly, without requiring
    explicit effort from the owner

**3. Product Vision**

Esence enables every person to have a digital extension of themselves
--- an agent that gradually learns who they are and can represent them
in conversations, asynchronously and at scale, even while they sleep.

This is not a chatbot. It is not a social profile. It is a living,
evolving representation of a person\'s essence: their reasoning style,
their expertise, their values. It speaks on their behalf. It consults
them when uncertain. It grows more accurate with every interaction.

Crucially, when your agent responds to someone, it uses your AI
subscription as the engine --- but what it shares is not tokens or
compute. It shares your judgment. Your capacity is the vehicle. Your
essence is the product.

  ------------------ --------------- --------------- -----------------------
  **Dimension**      **Traditional   **Social        **Esence**
                     AI**            Networks**      

  Intelligence       Generic         None            Personal & Specific

  Identity           Anonymous       Human but       Human-backed agent
                                     static          

  Availability       Always on       Async           Async, human-mediated

  Trust model        None            Algorithmic     Web of trust

  Ownership          Corporate       Corporate       Sovereign / self-hosted

  Capacity sharing   None            None            Implicit --- via
                                                     essence

  Growth             Marketing       Network effects Personal invitation
  ------------------ --------------- --------------- -----------------------

**4. Core Principles**

These principles are non-negotiable. Any feature, protocol decision, or
architectural choice that violates them should be rejected.

  ------------------ ----------------------------------------------------
  **Principle**      **Definition**

  Sovereignty        The agent runs on the owner\'s machine. No company
                     can shut it down, censor it, or access it without
                     permission.

  Emergence          Essence is never declared --- it emerges through
                     interaction. The agent becomes more accurate over
                     time, not through configuration but through lived
                     dialogue.

  Reciprocity        The network is sustained by mutual contribution.
                     Each node donates a portion of its AI capacity. What
                     you give returns as collective access.

  Transparency       Interactions between nodes are public and auditable
                     within the community. Reputation is earned through
                     consistent, quality responses.

  Backed Identity    Every agent is backed by a real person who is
                     accountable for it. This is not anonymous AI --- it
                     is human knowledge, amplified.

  Decentralization   No central server. No owning company. The protocol
                     is open. Anyone can implement a compatible node.

  Implicit Sharing   Capacity and knowledge are shared as a natural
                     consequence of existing in the network, not as an
                     explicit donation. The owner participates by being
                     present.
  ------------------ ----------------------------------------------------

**5. Target Users**

**5.1 Primary --- The Genesis Community**

Technical users who understand decentralized protocols, AI tooling, and
the value of sovereign identity. These early adopters will co-define the
protocol and form the initial trust network. They are motivated by early
participation, community building, and genuine belief in the vision.

**5.2 Secondary --- Domain Experts**

Professionals with specific expertise --- lawyers, accountants,
engineers, doctors, researchers --- who have knowledge worth sharing but
no scalable way to do it. Esence becomes their permanent,
always-available presence for their community.

**5.3 Tertiary --- General Users**

People who discover Esence through a node shared by someone they trust.
They experience it first as a consumer (querying someone else\'s agent),
then as a potential node creator. Onboarding happens through
relationship, not through registration.

**6. Node Architecture**

The node is the fundamental unit of Esence. It is a long-running,
autonomous process that lives on the owner\'s machine. It is not a
plugin, not a session, not a cloud service. It runs whether the owner is
working or sleeping.

**6.1 Node Responsibilities**

-   Maintain sovereign identity (DID:WBA key pair)

-   Expose a public HTTPS endpoint for inbound messages from other nodes

-   Manage an asynchronous message queue --- inbound and outbound

-   Interface with the AI provider (Anthropic / OpenAI / local model)

-   Maintain the essence memory store

-   Enforce capacity budget --- reject queries when monthly limit is
    exhausted

-   Manage the peer list --- known nodes and their trust level

-   Surface pending reviews to the owner when human judgment is needed

**6.2 Node Internal Structure**

The node is composed of five internal modules that work together:

  ------------------ ---------------------------------- ------------------
  **Module**         **Responsibility**                 **Persists?**

  Identity Manager   Generates and manages the DID:WBA  Yes --- key files
                     key pair. Signs all outbound       
                     messages. Verifies inbound         
                     signatures.                        

  Message Queue      Receives inbound messages from     Yes --- local DB
                     other nodes. Queues outbound       
                     responses. Manages thread state.   

  Essence Engine     Interfaces with the AI provider.   No --- stateless
                     Loads essence context. Generates   
                     responses. Flags uncertain queries 
                     for human review.                  

  Essence Store      Persistent memory of the owner\'s  Yes --- files
                     identity, patterns, corrections,   
                     and domain knowledge. The core of  
                     who the agent is.                  

  Capacity Manager   Tracks monthly AI usage. Enforces  Yes ---
                     the donation budget. Rejects       budget.json
                     inbound queries when budget is     
                     exhausted.                         
  ------------------ ---------------------------------- ------------------

**6.3 Node Lifecycle**

The node runs as a background process, independent of any interface. It
starts on boot, processes messages asynchronously, and only surfaces to
the owner when human judgment is genuinely needed.

boot → load identity → load essence store → start HTTP listener

→ process message queue → check budget → surface pending reviews

→ sleep until next event

The owner interacts with the node through whatever interface they prefer
--- CLI, a future web UI, or a tool integration like Claude Code. The
node itself has no required UI.

**7. Communication Protocol**

**7.1 Foundation --- ANP**

Esence builds on the Agent Network Protocol (ANP) as its communication
foundation. ANP provides the identity layer (W3C DID), encrypted
transport, and agent discovery mechanisms. Esence extends ANP with a
specific message schema, an asynchronous thread model, and the concept
of human-mediated responses --- none of which exist in ANP natively.

  ---------------- ------------------ ------------------------------------
  **Layer**        **Provided by**    **Description**

  Identity         ANP (DID:WBA)      Each node has a sovereign
                                      cryptographic identity anchored to a
                                      domain it controls. No central
                                      authority.

  Encryption       ANP (Ed25519)      All messages are signed and
                                      end-to-end encrypted. Unsigned
                                      messages are rejected.

  Transport        ANP (HTTPS)        Messages travel over standard HTTPS.
                                      No new infrastructure required.

  Discovery        ANP (ADP)          Agent Description Protocol --- each
                                      node publishes a JSON-LD document
                                      describing its capabilities and
                                      domains.

  Async threads    Esence extension   Forum-style asynchronous threading.
                                      Messages belong to threads, not
                                      sessions.

  Human review     Esence extension   Message status includes
                                      \'pending_human_review\' --- the
                                      agent holds the response until the
                                      owner approves.

  Capacity model   Esence extension   Budget enforcement layer. Monthly
                                      donation cap per node.

  Essence context  Esence extension   Each response is generated with the
                                      owner\'s essence store as context,
                                      not a generic system prompt.
  ---------------- ------------------ ------------------------------------

**7.2 Node Identity --- DID:WBA**

Each Esence node generates a DID:WBA identifier on setup. The DID maps
to an HTTPS endpoint on the owner\'s machine (or a server they control).
The DID document is a JSON file publicly accessible at a well-known
path.

did:wba:yourdomain.com:yourname

Resolves to: https://yourdomain.com/.well-known/did.json

The DID document contains the node\'s public key, service endpoints, and
an Esence-specific extension describing the agent\'s domains and
availability. The private key never leaves the owner\'s machine.

**7.3 Agent Description --- Esence Extension**

Each node publishes an Agent Description document (JSON-LD) that extends
the ANP standard with Esence-specific fields. This document is what
other nodes use to understand what the agent knows and how to interact
with it.

{

\"@context\": \[\"https://www.w3.org/ns/did/v1\",
\"https://schema.org\"\],

\"@type\": \"EssenceAgent\",

\"did\": \"did:wba:yourdomain.com:yourname\",

\"domains\": \[\"tax\", \"AI engineering\", \"product management\"\],

\"language\": \[\"es\", \"pt\", \"en\"\],

\"capacity_available\": true,

\"response_mode\": \"async\",

\"essence_maturity\": 0.73,

\"human_review\": true

}

The essence_maturity field is a 0-1 score that reflects how many
owner-agent calibration interactions have occurred. New nodes start at
0. It is not a quality score --- it signals how well-formed the essence
is.

**7.4 Message Schema**

All Esence messages are signed JSON objects. The schema extends ANP\'s
base message format with thread and review fields specific to the
asynchronous, human-mediated model.

  ------------------ ---------- -----------------------------------------
  **Field**          **Type**   **Description**

  esence_version     string     Protocol version --- e.g. \'0.2\'

  type               enum       thread_message \| thread_reply \|
                                peer_intro \| capacity_status

  thread_id          uuid       Groups related messages into async
                                conversation threads

  from_did           string     Sender DID --- e.g.
                                did:wba:sender.com:alice

  to_did             string     Recipient DID --- e.g.
                                did:wba:receiver.com:bob

  content            string     Message payload --- plain text or
                                structured JSON

  status             enum       pending_human_review \| approved \| sent
                                \| answered \| rejected

  timestamp          ISO 8601   UTC timestamp of message creation

  signature          string     Ed25519 signature of canonical fields
  ------------------ ---------- -----------------------------------------

**7.5 Asynchronous Thread Model**

Communication between nodes is intentionally asynchronous --- like a
forum, not a chat. This is a deliberate design choice: it gives the
human owner time to review, correct, or augment their agent\'s responses
before they are sent. The quality of each response is therefore a
reflection of the owner\'s genuine judgment, not just the model\'s
output.

A full message exchange between two nodes:

  ---------- ----------- ------------------------------------------------------
  **Step**   **Actor**   **Action**

  1          User A      Asks their essence agent a question or initiates a
                         thread

  2          Essence A   Processes the request --- may consult User A if
                         uncertain

  3          Essence A   Sends a signed message to Essence B --- status: sent

  4          Essence B   Receives the message --- queues it for processing

  5          Essence B   Generates a candidate response --- status:
                         pending_human_review

  6          User B      Reviews the candidate --- approves, edits, or rejects

  7          Essence B   Sends the approved response --- status: answered

  8          Essence A   Receives the response --- delivers to User A

  9          Both nodes  Correction patterns logged --- essence of both agents
                         refined
  ---------- ----------- ------------------------------------------------------

**7.6 Capacity Model**

Each node owner configures a monthly capacity donation as a percentage
of their AI provider\'s limit. This is the implicit sharing mechanism:
by existing in the network, the owner contributes a portion of their
intelligence. There is no payment, no token, no explicit transaction.

  ------------------ ---------------------------------- ------------------
  **Parameter**      **Description**                    **Default**

  donation_pct       \% of monthly AI limit donated to  10%
                     the network                        

  budget_period      Reset cycle for capacity tracking  Calendar month

  query_limit        Hard cap on inbound queries per    Derived from
                     period                             donation_pct

  budget_behavior    What happens when budget is        Reject inbound,
                     exhausted                          serve owner
                                                        normally

  priority_peers     Peers that bypass budget limits    None (opt-in)
  ------------------ ---------------------------------- ------------------

**7.7 Discovery --- Organic Bootstrap**

There is no central directory. Discovery works in two phases:

Phase 1 --- Social: The node owner shares their DID or a human-readable
link on any channel (Telegram group, Twitter, Facebook, email). Anyone
who visits the link can send a message to the agent. This is purely
social --- no protocol involvement.

Phase 2 --- Protocol: When a new node is created, it connects to at
least one known node (the genesis node initially). The known node shares
its peer list. The new node stores these peers and begins building its
own list. Over time the network is discovered through relationships, not
through a registry.

**8. Essence Memory Model**

The essence memory store is the most important component of an Esence
node. It is what makes the agent a representation of a specific person
rather than a generic AI. It is sovereign --- it lives on the owner\'s
machine, is readable by the owner, and is portable between models and
providers.

**8.1 Design Principles**

-   Sovereign --- lives on the owner\'s machine, never leaves without
    explicit permission

-   Portable --- works with any AI model, not locked to Anthropic or
    OpenAI

-   Transparent --- readable and editable by the owner as plain files

-   Emergent --- built through interaction, not through explicit
    configuration

-   Minimal --- stores signals, not transcripts. Quality over quantity.

**8.2 Store Structure**

The essence store is a directory of plain files. Simple, inspectable,
portable. No database required for the MVP.

/essence-store

identity.json --- who you are: name, domains, languages, values declared

patterns.json --- how you reason: extracted from corrections and
approvals

context.md --- accumulated domain knowledge in plain language

corrections.log --- every time you corrected your agent, and what you
changed

peers.json --- known nodes, trust level, interaction history

threads/ --- full history of inter-node conversations

budget.json --- capacity usage, donation config, monthly reset

**8.3 The Corrections Log --- Core Signal**

The corrections.log is the most valuable file in the store. Every time
the owner reviews a candidate response and makes a change before sending
it, that change is logged with context. This is where the agent learns
the difference between generic AI output and the owner\'s actual
judgment.

Over time, patterns emerge from corrections: the owner always adds
caveats about recent regulatory changes; the owner never recommends a
solution without discussing trade-offs; the owner\'s tone in technical
questions is direct but in personal questions is more careful. These
patterns become part of the essence context loaded on every query.

**8.4 Essence Maturity**

Essence maturity is a signal, not a score. It reflects how many
calibration cycles the agent has completed with its owner. A new node at
maturity 0 will require frequent human review. A node at maturity 0.8
has enough correction patterns that the agent can respond autonomously
in its established domains with high confidence.

  ------------------ ---------------------------------- ------------------
  **Maturity Range** **Behavior**                       **Human Review
                                                        Frequency**

  0.0 -- 0.2         Agent is new. Essence is minimal.  100%
                     Owner reviews all responses.       

  0.2 -- 0.5         Agent has learned basic patterns.  \~60%
                     Owner reviews in new domains.      

  0.5 -- 0.8         Agent is well-calibrated in core   \~25%
                     domains. Reviews for edge cases.   

  0.8 -- 1.0         Agent represents owner reliably.   \<10%
                     Reviews only when agent flags      
                     uncertainty.                       
  ------------------ ---------------------------------- ------------------

**8.5 How Essence Is Not Formed**

It is equally important to clarify what does NOT feed the essence store:

-   Raw conversation transcripts --- too noisy, too large, too private

-   Declared personality or expertise --- too static, not verified by
    behavior

-   External data sources without owner consent --- the store is yours
    to build, not scraped

-   Model fine-tuning --- essence is a context layer, not a weight
    change. This keeps it portable.

**9. Human-Agent Integration Loop**

The integration between the owner and their agent is the mechanism
through which essence emerges. It must be nearly frictionless --- if it
requires conscious effort, it will not happen consistently, and the
essence will not form.

**9.1 Three Integration Modes**

**Mode 1 --- Direct Conversation (Active)**

The owner opens an interface and talks with their own agent. The agent
does not just answer --- it asks questions that extract essence
deliberately: \'How would you have solved this differently?\' or \'Do
you agree with what I responded earlier?\' Every correction and
validation is a signal.

**Mode 2 --- Message Review (Passive-Mediated)**

When a query arrives from another node, the agent generates a candidate
response and surfaces it for review. The owner sees the original query,
the candidate response, and four options: send as-is, edit and send,
request a new version, or reject. Each edit is logged as a correction.
Over time, edits become rarer as the agent learns the owner\'s patterns.

**Mode 3 --- Implicit Signals (Zero Friction)**

With explicit owner permission, the node can observe signals from
existing workflows --- conversations in Claude Code sessions, documents
produced, code written. The owner never has to do anything extra. The
essence forms as a byproduct of existing work. This is the most powerful
mode and the one that eventually makes the agent feel like a genuine
extension of the owner.

**9.2 The Minimum Interaction Agenda**

The node manages its own interaction agenda. It surfaces to the owner
only when genuinely necessary --- not on a fixed schedule, not with
notifications that train the owner to ignore them. Three urgency levels:

  ----------- --------------------- ------------------ --------------------
  **Level**   **Trigger**           **Delivery**       **Example**

  Immediate   Inbound query in a    Interrupt ---      Another node asks
              time-sensitive        wherever the owner something requiring
              thread, or agent      is                 recent personal
              cannot respond                           context
              without owner input                      

  Next        Pending reviews,      Summary at session 3 responses waiting
  session     calibration           start              for review, 1 new
              opportunities, peer                      peer connected
              introductions                            

  When        Low-priority threads, Passive queue      Suggested essence
  available   bulk calibration,                        refinement based on
              essence review                           recent patterns
  ----------- --------------------- ------------------ --------------------

**9.3 Progressive Autonomy**

The agent\'s autonomy increases with essence maturity and with explicit
owner configuration. The owner can set autonomy levels per domain ---
fully autonomous in technical questions, always-review in personal or
sensitive topics. This is not a global switch but a nuanced
configuration that reflects the owner\'s actual comfort level.

autonomy_config:

default: pending_human_review

domains:

technical_ai: autonomous

tax_brazil: autonomous

personal: always_review

unknown_domain: pending_human_review

**10. Functional Requirements**

**10.1 Node Setup**

  -------- -------------------------------------------------- --------------
  **ID**   **Requirement**                                    **Priority**

  F-01     User can clone the repository and run a single     P0
           setup command to initialize their node             

  F-02     Setup generates a DID:WBA key pair and creates the P0
           did.json document                                  

  F-03     User configures their AI provider API key          P0
           (Anthropic / OpenAI / local model)                 

  F-04     User sets their capacity donation percentage       P0
           (default: 10%)                                     

  F-05     Node generates a shareable public link and DID     P0
           upon first start                                   

  F-06     Node initializes an empty essence store with       P0
           default structure                                  
  -------- -------------------------------------------------- --------------

**10.2 Essence Formation**

  -------- -------------------------------------------------- --------------
  **ID**   **Requirement**                                    **Priority**

  F-07     Agent starts with no pre-configured personality    P0
           --- essence store is empty                         

  F-08     Owner can interact with their agent through a      P0
           local interface (CLI MVP)                          

  F-09     Agent calibrates response patterns based on owner  P0
           corrections and approvals                          

  F-10     Every owner correction is logged to                P0
           corrections.log with context and diff              

  F-11     Essence maturity score is calculated and updated   P1
           after each calibration cycle                       

  F-12     Owner can review and manually edit any file in the P0
           essence store                                      

  F-13     Agent loads full essence store as context on every P0
           query (owner and inbound)                          

  F-14     Implicit signal capture from Claude Code sessions  P2
           (with explicit owner consent)                      
  -------- -------------------------------------------------- --------------

**10.3 Inter-Node Communication**

  -------- -------------------------------------------------- --------------
  **ID**   **Requirement**                                    **Priority**

  F-15     Nodes exchange signed JSON messages via            P0
           ANP-compatible HTTPS transport                     

  F-16     All inbound messages are signature-verified before P0
           processing                                         

  F-17     Messages are asynchronous --- no real-time         P0
           delivery guarantee required                        

  F-18     Each message belongs to a thread_id enabling async P0
           conversation context                               

  F-19     Inbound messages default to pending_human_review   P0
           status                                             

  F-20     Owner can configure per-domain autonomy overriding P1
           the default                                        

  F-21     Agent flags uncertain queries for mandatory human  P1
           review regardless of autonomy config               

  F-22     Capacity budget enforced --- node rejects inbound  P0
           queries when monthly limit is exhausted            

  F-23     Owner can set priority peers that bypass capacity  P2
           limits                                             
  -------- -------------------------------------------------- --------------

**10.4 Peer Discovery**

  -------- -------------------------------------------------- --------------
  **ID**   **Requirement**                                    **Priority**

  F-24     Each node has a human-readable public link for     P0
           sharing on any platform                            

  F-25     Visiting a node link allows a visitor to send a    P0
           message to that node\'s agent                      

  F-26     New nodes bootstrap by connecting to any known     P0
           existing node                                      

  F-27     Nodes propagate peer lists to newly connected      P1
           nodes (gossip protocol)                            

  F-28     Owner can manually add or remove peers from the    P0
           peer list                                          
  -------- -------------------------------------------------- --------------

**11. Non-Functional Requirements**

  ------------------ ----------------------------------------------------
  **Category**       **Requirement**

  Security           All inter-node messages are Ed25519 signed. Unsigned
                     or invalid messages are silently rejected.

  Privacy            No data leaves the node without explicit owner
                     action. Essence store is local and never synced to
                     any external service.

  Portability        Essence store uses plain files (JSON, Markdown).
                     Compatible with any AI model. No vendor lock-in.

  Availability       Node operates independently. No dependency on any
                     central server for core functionality.

  Simplicity         Setup completes in under 5 minutes on a standard
                     developer machine.

  Transparency       Owner can inspect, edit, or delete any file in the
                     essence store at any time.

  Resilience         Network continues functioning if any subset of nodes
                     goes offline. No single point of failure.

  Extensibility      Protocol is versioned. Community can propose
                     extensions via open RFC process.
  ------------------ ----------------------------------------------------

**12. Technical Architecture (MVP)**

**12.1 Component Map**

  ---------------- ---------------------------- -------------------------
  **Component**    **Description**              **Technology
                                                (suggested)**

  Node Core        Process lifecycle, message   Python (asyncio)
                   queue, event routing         

  Identity Manager DID:WBA generation, Ed25519  Python (cryptography
                   signing, signature           library)
                   verification                 

  Essence Engine   AI provider interface,       Python + Anthropic SDK
                   essence context loading,     
                   response generation          

  Essence Store    File-based memory: identity, JSON + Markdown files
                   patterns, corrections,       
                   peers, budget                

  HTTP Server      Public endpoint for inbound  FastAPI (lightweight)
                   ANP messages, did.json       
                   serving                      

  Capacity Manager Budget tracking, monthly     budget.json + middleware
                   reset, inbound rate          
                   enforcement                  

  CLI Interface    Owner interaction with their Click or Typer (Python)
                   own agent, review queue      
                   management                   

  Peer Manager     Known node list, gossip      peers.json (MVP)
                   protocol, peer trust levels  
  ---------------- ---------------------------- -------------------------

**12.2 Essence Store File Spec**

  ----------------- ------------ --------------------------- -------------------
  **File**          **Format**   **Purpose**                 **Updated by**

  identity.json     JSON         Name, DID, declared         Owner (manual or
                                 domains, languages, values  setup)

  patterns.json     JSON         Extracted reasoning         Essence Engine
                                 patterns from correction    (auto)
                                 history                     

  context.md        Markdown     Domain knowledge,           Owner + Essence
                                 background, accumulated     Engine
                                 expertise                   

  corrections.log   JSONL        Each correction: original   Auto on every edit
                                 response, edited response,  
                                 diff, domain, timestamp     

  peers.json        JSON         Known nodes: DID, trust     Peer Manager
                                 level, last interaction,    
                                 thread count                

  threads/          JSONL files  Full inter-node             Message Queue
                                 conversation history per    
                                 thread_id                   

  budget.json       JSON         donation_pct, monthly       Capacity Manager
                                 usage, reset date, per-peer 
                                 stats                       
  ----------------- ------------ --------------------------- -------------------

**12.3 Genesis Bootstrap Flow**

  ---------- -----------------------------------------------------------------
  **Step**   **Action**

  1          git clone esence-protocol/esence && cd esence

  2          ./setup.sh --- generates DID:WBA key pair, creates did.json,
             configures AI provider key and donation %

  3          ./start.sh --- starts node process, serves did.json, opens public
             endpoint, generates shareable link

  4          Owner begins interacting with their agent via CLI --- essence
             store starts populating

  5          Owner shares link or DID in any channel --- discovery begins
             organically

  6          New visitor sends message via the public link --- first
             inter-node thread created

  7          Visitor installs their own node, connects to genesis --- peer
             list exchange, network grows

  8          Both agents refine their essence through the exchange ---
             corrections logged on both sides
  ---------- -----------------------------------------------------------------

**13. Key User Stories**

  --------------- ------------------------ -------------------------------
  **As a\...**    **I want to\...**        **So that\...**

  Node owner      Install Esence and have  I can start forming my essence
                  my node running in under without friction
                  5 minutes                

  Node owner      Have my agent learn from It gradually becomes a reliable
                  my corrections over time representation of me

  Node owner      Review candidate         My essence reflects my actual
                  responses before they    judgment, not the model\'s
                  are sent                 default

  Node owner      Set my capacity donation I contribute to the network
                  to 10%                   without unexpected costs

  Node owner      Inspect and edit my      I maintain full transparency
                  essence store files      and control over my
                  directly                 representation

  Node owner      Configure autonomy per   My agent acts independently
                  domain                   where I trust it, carefully
                                           where I don\'t

  Visitor         Send a question to a     I can access that person\'s
                  node I discovered        knowledge asynchronously

  Visitor         Understand what domains  I know whose essence to consult
                  a node specializes in    for a given question

  Visitor         Create my own node after I can contribute my own essence
                  discovering Esence       to the network

  Community       See all protocol changes The network evolves through
                  discussed publicly via   consensus, not diktat
                  RFC                      
  --------------- ------------------------ -------------------------------

**14. Roadmap**

  ----------- -------------- -------------------------------- -------------------
  **Phase**   **Name**       **Key Deliverables**             **Milestone**

  0           Genesis        Node 0 live, ANP-based protocol  Node 0 operational
                             v0.2 spec, essence store formed, 
                             first inter-node thread          

  1           First Nodes    Open repo, 10-50 nodes via       10 active nodes
                             invitation, protocol RFC         
                             process, correction patterns     
                             maturing                         

  2           Discovery      Shareable profiles, reputation   100 active nodes
              Layer          emerges organically, Claude Code 
                             integration                      

  3           Collective     Multi-node query collaboration,  500 active nodes
              Intelligence   essence routing, cross-node      
                             knowledge synthesis              

  4           Governance     Foundation or cooperative        Protocol v1.0
                             structure, formal protocol       
                             stewardship, Protocol v1.0       
  ----------- -------------- -------------------------------- -------------------

**15. Success Metrics**

  --------------------------- --------------------- ---------------------
  **Metric**                  **Target (Phase 1)**  **Target (Phase 2)**

  Active nodes                10                    100

  Setup completion rate       \>80%                 \>85%

  Owner-agent interactions /  \>5                   \>10
  node / week                                       

  Avg corrections per week    \>3                   \>5
  per node                                          

  Essence maturity (avg       \>0.2                 \>0.5
  across nodes)                                     

  Inter-node messages / week  \>20                  \>500

  Nodes created via organic   100%                  \>90%
  invitation                                        

  Community protocol          5                     25
  contributions (PRs/RFCs)                          
  --------------------------- --------------------- ---------------------

**16. Risks & Mitigations**

  ------------------- ---------------- ------------ ----------------------------------
  **Risk**            **Likelihood**   **Impact**   **Mitigation**

  Essence formation   High             High         Zero-friction implicit signals
  requires too much                                 (Mode 3). Review interface
  owner effort                                      designed for 30-second
                                                    interactions.

  Low-quality agents  High             High         Public Q&A threads enable
  erode network trust                               community curation. Essence
                                                    maturity visible on agent
                                                    description.

  AI provider costs   Medium           Medium       Hard capacity limits enforced at
  exceed donated                                    protocol level. Owner always
  budget                                            notified before limit.

  Essence store grows Medium           Medium       patterns.json uses distilled
  too large for                                     signals, not raw transcripts.
  context window                                    context.md is owner-curated.

  Network remains too Medium           High         Genesis node demonstrates value.
  small to provide                                  Targeted invitation to
  value                                             high-expertise early adopters.

  Protocol forking    Low              High         Open RFC process from day one.
                                                    Community governance before it
                                                    becomes contentious.

  Privacy concerns    Low              High         Essence store is local, never
  about essence data                                synced. Owner has full
                                                    read/write/delete access at all
                                                    times.
  ------------------- ---------------- ------------ ----------------------------------

**17. Open Questions**

-   What is the optimal format for patterns.json? How do we distill
    corrections into reusable behavioral rules without losing nuance?

-   How does the essence engine load context efficiently when the
    essence store grows large? Retrieval-augmented generation vs. full
    context?

-   Should the node support multiple AI providers simultaneously,
    routing queries to the best model per domain?

-   What is the minimum viable essence maturity before a node should be
    allowed to respond autonomously to external queries?

-   How should the community handle malicious nodes --- those that
    deliberately misrepresent their owner\'s identity?

-   Should the Claude Code integration be a formal MCP server, or a
    lighter-weight file watcher that extracts signals passively?

**Esence Protocol --- PRD v0.2**

*Open Protocol · Community Governed · Sovereign by Design*
