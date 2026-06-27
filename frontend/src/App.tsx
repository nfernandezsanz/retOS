import {
  Activity,
  Bot,
  Database,
  FileSearch,
  LockKeyhole,
  Radio,
  ServerCog,
} from "lucide-react";
import "./styles.css";

const pipelineSteps = [
  { label: "Scan", value: "Discover mounted files and uploads", state: "ready" },
  { label: "Hash", value: "Create deterministic content identities", state: "ready" },
  { label: "OCR", value: "Extract text from scanned pages locally", state: "waiting" },
  { label: "Index", value: "Build rebuildable Tantivy BM25 projections", state: "waiting" },
];

const metrics = [
  { label: "Domains", value: "0", icon: Database },
  { label: "Documents", value: "0", icon: FileSearch },
  { label: "Active jobs", value: "0", icon: Activity },
  { label: "Provider", value: "Ollama", icon: Bot },
];

function App() {
  return (
    <main className="shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <div className="brand">
          <ServerCog aria-hidden="true" />
          <span>RetOS</span>
        </div>
        <nav>
          <a href="#overview">Overview</a>
          <a href="#documents">Documents</a>
          <a href="#queries">Queries</a>
          <a href="#audit">Audit</a>
          <a href="#admin">Admin</a>
        </nav>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Local-first research console</p>
            <h1>Auditable document investigation</h1>
          </div>
          <button type="button" className="primary-action">
            <Radio aria-hidden="true" />
            Connect live updates
          </button>
        </header>

        <section className="metrics" aria-label="System metrics">
          {metrics.map((metric) => {
            const Icon = metric.icon;
            return (
              <article className="metric" key={metric.label}>
                <Icon aria-hidden="true" />
                <div>
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                </div>
              </article>
            );
          })}
        </section>

        <section className="content-grid">
          <article className="panel" id="documents">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Pipeline</p>
                <h2>Processing timeline</h2>
              </div>
              <span className="status-pill">Idle</span>
            </div>
            <ol className="timeline" aria-live="polite">
              {pipelineSteps.map((step) => (
                <li key={step.label} className={step.state}>
                  <strong>{step.label}</strong>
                  <span>{step.value}</span>
                </li>
              ))}
            </ol>
          </article>

          <article className="panel" id="queries">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Research</p>
                <h2>Query workspace</h2>
              </div>
              <span className="status-pill local">Local model</span>
            </div>
            <label className="query-box">
              <span>Question</span>
              <textarea placeholder="Ask a grounded question about the indexed corpus." />
            </label>
            <button type="button" className="secondary-action">
              <Bot aria-hidden="true" />
              Run with Gemma 4
            </button>
          </article>

          <article className="panel wide" id="audit">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">Audit</p>
                <h2>Evidence ledger</h2>
              </div>
              <span className="status-pill">No runs yet</span>
            </div>
            <div className="empty-state">
              <LockKeyhole aria-hidden="true" />
              <p>
                Agent runs will appear here with tool calls, cited segments, answer hashes,
                and budget usage.
              </p>
            </div>
          </article>
        </section>
      </section>
    </main>
  );
}

export default App;
