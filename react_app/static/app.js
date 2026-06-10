const { useEffect, useMemo, useState } = React;

const emptyMetrics = {
  similarAppointments: 0,
  medications: 0,
  quantityNeeded: 0,
  kgEvidence: 0,
  noiseFloor: 3,
  graphNodes: 0,
  graphRelationships: 0,
  database: "neo4j",
};

const defaultVendors = ["Amazon", "Chewy", "Covetrus", "MWI", "Patterson", "Med-Vet International", "Use KG supplier"];

function todayPlus(days) {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function fileStem(filters) {
  const vendor = (filters.vendor || "Amazon").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  return `florida_plantation_medication_inventory_${vendor || "vendor"}_${filters.appointmentDate || todayPlus(7)}`;
}

function App() {
  const [bootstrap, setBootstrap] = useState(null);
  const [filters, setFilters] = useState({
    appointmentReason: "vomiting",
    appointmentDate: todayPlus(7),
    historyStart: "",
    historyEnd: "",
    maxSimilar: 80,
    species: "all",
    lifeStage: "all",
    forecastScope: "whole_episode",
    includeProcedural: false,
    minCases: 3,
    vendor: "Amazon",
  });
  const [payload, setPayload] = useState({
    clinicName: "Florida Plantation Clinic",
    inventory: [],
    similarAppointments: [],
    medicationEvidence: [],
    provenance: [],
    forecastRules: [],
    metrics: emptyMetrics,
    purchaseDate: todayPlus(5),
    vendor: "Amazon",
    vendorOptions: defaultVendors,
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [chatOpen, setChatOpen] = useState(false);
  const [chatInput, setChatInput] = useState("");
  const [chatBusy, setChatBusy] = useState(false);
  const [cartBusy, setCartBusy] = useState(false);
  const [cartResult, setCartResult] = useState(null);
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: "Ask about medication quantities, suppliers, price gaps, or why a medication is on the sheet.",
    },
  ]);

  const requestFilters = useMemo(() => filters, [filters]);
  const availableLifeStages = bootstrap?.lifeStages?.[filters.species] || bootstrap?.lifeStages?.all || ["all"];

  async function loadBootstrap() {
    const response = await fetch("/api/bootstrap");
    if (!response.ok) throw new Error("Could not load graph metadata.");
    const data = await response.json();
    setBootstrap(data);
    setFilters((current) => ({
      ...current,
      appointmentReason: data.suggestions?.[0] || current.appointmentReason,
      appointmentDate: data.defaultAppointmentDate || current.appointmentDate,
      historyStart: data.defaultHistoryStart || current.historyStart,
      historyEnd: data.maxHistoryDate || current.historyEnd,
      species: current.species || "all",
      lifeStage: current.lifeStage || "all",
      vendor: current.vendor || "Amazon",
    }));
  }

  async function loadInventory(nextFilters = requestFilters) {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/inventory", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(nextFilters),
      });
      if (!response.ok) throw new Error("Could not build inventory sheet.");
      const data = await response.json();
      setPayload(data);
    } catch (err) {
      setError(err.message || "Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadBootstrap().catch((err) => {
      setError(err.message || "Could not initialize app.");
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (filters.historyStart && filters.historyEnd) {
      loadInventory(filters);
    }
  }, [
    filters.appointmentReason,
    filters.appointmentDate,
    filters.historyStart,
    filters.historyEnd,
    filters.maxSimilar,
    filters.species,
    filters.lifeStage,
    filters.forecastScope,
    filters.includeProcedural,
    filters.minCases,
    filters.vendor,
  ]);

  function updateFilter(name, value) {
    if (name === "vendor") setCartResult(null);
    setFilters((current) => {
      const next = { ...current, [name]: value };
      if (name === "species") next.lifeStage = "all";
      return next;
    });
  }

  async function exportSheet(type) {
    const response = await fetch(`/api/export/${type}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(requestFilters),
    });
    if (!response.ok) {
      setError(`Could not export ${type.toUpperCase()}.`);
      return;
    }
    const blob = await response.blob();
    downloadBlob(blob, `${fileStem(filters)}.${type === "xlsx" ? "xlsx" : type}`);
  }

  async function sendMessage(event) {
    event.preventDefault();
    const question = chatInput.trim();
    if (!question || chatBusy) return;
    const nextMessages = [...messages, { role: "user", content: question }];
    setMessages(nextMessages);
    setChatInput("");
    setChatBusy(true);
    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, filters: requestFilters, history: nextMessages }),
      });
      if (!response.ok) throw new Error("Chat request failed.");
      const data = await response.json();
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: data.answer,
          source: data.source,
        },
      ]);
    } catch (err) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: err.message || "The chat loop failed.",
          source: "error",
        },
      ]);
    } finally {
      setChatBusy(false);
    }
  }

  async function createVendorCart(automate = false, visible = false) {
    setCartBusy(true);
    setCartResult(null);
    setError("");
    try {
      const response = await fetch("/api/vendor-cart", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filters: requestFilters, itemLimit: 3, automate, visible }),
      });
      if (!response.ok) throw new Error("Could not create vendor cart draft.");
      setCartResult(await response.json());
    } catch (err) {
      setError(err.message || "Vendor cart request failed.");
    } finally {
      setCartBusy(false);
    }
  }

  const metrics = payload.metrics || emptyMetrics;
  const hasRows = payload.inventory?.length > 0;
  const vendorOptions = payload.vendorOptions || bootstrap?.vendorOptions || defaultVendors;
  const selectedVendor = payload.vendor || filters.vendor || "Amazon";
  const vendorInvoice = payload.vendorInvoice || [];
  const previewRows = vendorInvoice.slice(0, 3);
  const cartStatusLabel = {
    cart_complete: "Cart complete",
    cart_partial: "Cart partially complete",
    cart_stopped: "Cart stopped",
    draft_ready: "Cart draft ready",
  }[cartResult?.status] || "Cart update";

  return (
    <main>
      <section className="hero">
        <div>
          <div className="eyebrow">{payload.clinicName || "Florida Plantation Clinic"}</div>
          <h1>Medication Inventory Tracker</h1>
          <p>
            Forecast medication inventory from future appointment complaints using the knowledge graph's clinical
            sign chain, cohort filters, and traceable historical medication paths.
          </p>
        </div>
        <div className="heroBadge">
          <span>KG</span>
          <strong>{metrics.database || "neo4j"}</strong>
        </div>
      </section>

      <section className="controls">
        <div className="controlHeading">Forecast setup</div>
        <div className="primaryControlGrid">
          <label className="wide">
            Presenting complaint
            <input
              list="complaintSuggestions"
              value={filters.appointmentReason}
              onChange={(event) => updateFilter("appointmentReason", event.target.value)}
              placeholder="Example: vomiting, pruritus, dental calculus, wellness exam"
            />
            <datalist id="complaintSuggestions">
              {(bootstrap?.suggestions || ["vomiting"]).map((suggestion) => (
                <option key={suggestion} value={suggestion} />
              ))}
            </datalist>
          </label>
          <label>
            Species
            <select value={filters.species} onChange={(event) => updateFilter("species", event.target.value)}>
              {(bootstrap?.species || ["all", "canine", "feline"]).map((species) => (
                <option key={species} value={species}>{species === "all" ? "All species" : species}</option>
              ))}
            </select>
          </label>
          <label>
            Future appointment date
            <input
              type="date"
              min={new Date().toISOString().slice(0, 10)}
              value={filters.appointmentDate}
              onChange={(event) => updateFilter("appointmentDate", event.target.value)}
            />
          </label>
        </div>
        <details className="advancedControls">
          <summary>Advanced forecast settings</summary>
          <div className="advancedGrid">
            <label>
              Life stage
              <select value={filters.lifeStage} onChange={(event) => updateFilter("lifeStage", event.target.value)}>
                {availableLifeStages.map((stage) => (
                  <option key={stage} value={stage}>{stage === "all" ? "All stages" : stage}</option>
                ))}
              </select>
            </label>
            <label>
              History start
              <input
                type="date"
                min={bootstrap?.minHistoryDate || ""}
                max={bootstrap?.maxHistoryDate || ""}
                value={filters.historyStart}
                onChange={(event) => updateFilter("historyStart", event.target.value)}
              />
            </label>
            <label>
              History end
              <input
                type="date"
                min={bootstrap?.minHistoryDate || ""}
                max={bootstrap?.maxHistoryDate || ""}
                value={filters.historyEnd}
                onChange={(event) => updateFilter("historyEnd", event.target.value)}
              />
            </label>
            <label>
              Forecast scope
              <select value={filters.forecastScope} onChange={(event) => updateFilter("forecastScope", event.target.value)}>
                <option value="whole_episode">Whole episode</option>
                <option value="day1">Day 1 only</option>
              </select>
            </label>
            <label>
              Max similar
              <input
                type="number"
                min="10"
                max="300"
                step="10"
                value={filters.maxSimilar}
                onChange={(event) => updateFilter("maxSimilar", Number(event.target.value))}
              />
            </label>
            <label>
              Min support cases
              <input
                type="number"
                min="1"
                max="20"
                step="1"
                value={filters.minCases}
                onChange={(event) => updateFilter("minCases", Number(event.target.value))}
              />
            </label>
            <label className="checkboxLine">
              Include procedural meds
              <input
                type="checkbox"
                checked={filters.includeProcedural}
                onChange={(event) => updateFilter("includeProcedural", event.target.checked)}
              />
            </label>
          </div>
        </details>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="metrics">
        <Metric label="Similar cases" value={metrics.similarAppointments} detail="sign-tag matched appointments" color="#2563eb" />
        <Metric label="Inventory rows" value={metrics.medications} detail={`${metrics.quantityNeeded || 0} total predicted units`} color="#0f766e" />
        <Metric label="Purchase by" value={payload.purchaseDate || "-"} detail="based on appointment date" color="#475569" small />
        <Metric label="KG evidence" value={metrics.kgEvidence} detail="historical medication rows" color="#7c3aed" />
      </section>

      <section className="sheetTop">
        <div>
          <h2>Medication inventory sheet</h2>
          <p>
            {payload.clinicName} · {payload.inventory?.length || 0} medications · {selectedVendor} · purchase by {payload.purchaseDate}
          </p>
        </div>
        <span className={hasRows ? "status ready" : "status"}>{hasRows ? "Ready to export" : "No rows to export"}</span>
      </section>

      <section className="vendorPanel">
        <div className="vendorToolbar">
          <label className="vendorSelector">
            Vendor invoice
            <select value={filters.vendor} onChange={(event) => updateFilter("vendor", event.target.value)}>
              {vendorOptions.map((vendor) => (
                <option key={vendor} value={vendor}>{vendor}</option>
              ))}
            </select>
          </label>
          <button disabled={!hasRows || cartBusy} onClick={() => createVendorCart(false, false)}>Create cart draft</button>
          <button disabled={!hasRows || cartBusy} onClick={() => createVendorCart(true, true)}>Open website and add cart</button>
        </div>
        <div className="vendorSummary">
          <b>{selectedVendor} invoice</b>
          <span>
            {Math.min(3, vendorInvoice.length || 0)} rows · {payload.vendorWebsite || "KG supplier"} · {payload.vendorCartMode || "vendor draft"}
          </span>
        </div>
        <VendorInvoiceTable rows={previewRows} />
        {cartResult ? (
          <div className={`cartResult ${cartResult.status || ""}`}>
            <b>{cartStatusLabel}</b>
            <span>{cartResult.message}</span>
            {cartResult.results?.length ? (
              <div className="cartResultList">
                <span>
                  Added: {cartResult.results
                    .filter((row) => String(row.status || "").startsWith("added_to_cart"))
                    .map((row) => row["Medication Name"])
                    .join(", ") || "No items confirmed"}
                </span>
              </div>
            ) : null}
          </div>
        ) : null}
      </section>

      <section className="sheet">
        <div className="sheetHeader">
          <div>
            <h3>Medication Inventory Tracker</h3>
            <p>Presenting complaint: {payload.appointmentReason || filters.appointmentReason}</p>
          </div>
          <strong>Purchase by {payload.purchaseDate}</strong>
        </div>
        <div className="metaRows">
          <div><b>Clinic</b><span>{payload.clinicName}</span></div>
          <div><b>Appointment Date</b><span>{payload.appointmentDate}</span></div>
          <div><b>Cohort</b><span>{payload.species || filters.species} · {payload.lifeStage || filters.lifeStage}</span></div>
          <div><b>Scope</b><span>{payload.forecastScope === "day1" ? "Day 1 only" : "Whole episode"}</span></div>
          <div><b>Vendor</b><span>{selectedVendor}</span></div>
        </div>
        <InventoryTable rows={payload.inventory || []} loading={loading} />
        <div className="notes">
          <b>Notes</b>
          <span>
            Medications come from sign-tag matched historical cases. Supplier follows the selected vendor; prices stay
            marked as quote needed until vendor pricing is loaded.
          </span>
        </div>
      </section>

      <section className="exportBar">
        <div className="exportTitle">Export inventory sheet</div>
        <div className="exportActions">
          <button disabled={!hasRows} onClick={() => exportSheet("pdf")}>PDF</button>
          <button disabled={!hasRows} onClick={() => exportSheet("xlsx")}>Excel</button>
          <button disabled={!hasRows} onClick={() => exportSheet("csv")}>CSV</button>
          <span>Exports use the selected vendor and the rows shown above for the {payload.appointmentDate} appointment.</span>
        </div>
      </section>

      <section className="evidence">
        <details>
          <summary>Forecast method</summary>
          <div className="methodGrid">
            {(payload.forecastRules || []).map((rule) => (
              <span className="ruleChip" key={rule}>{rule}</span>
            ))}
            <span className="ruleChip">
              {filters.forecastScope === "day1" ? "Day-1 medication demand" : "Whole-episode medication demand"}
            </span>
          </div>
        </details>
        <details open>
          <summary>Why these medications are on the sheet</summary>
          <EvidenceTable title="Forecast support by medication" rows={payload.provenance || []} />
        </details>
        <details>
          <summary>Matched appointments and medication paths</summary>
          <div className="evidenceGrid">
            <EvidenceTable title="Sign-tag matched appointments" rows={payload.similarAppointments || []} />
            <EvidenceTable title="Historical medication path rows" rows={payload.medicationEvidence || []} />
          </div>
        </details>
      </section>

      <ChatWidget
        open={chatOpen}
        setOpen={setChatOpen}
        messages={messages}
        chatInput={chatInput}
        setChatInput={setChatInput}
        sendMessage={sendMessage}
        busy={chatBusy}
      />
    </main>
  );
}

function Metric({ label, value, detail, color, small = false }) {
  return (
    <div className="metric" style={{ borderTopColor: color }}>
      <div className="metricLabel">{label}</div>
      <div className={small ? "metricValue small" : "metricValue"}>{value}</div>
      <div className="metricDetail">{detail}</div>
    </div>
  );
}

function InventoryTable({ rows, compact = false, loading = false }) {
  const headers = [
    "Medication Name",
    "Product Type",
    "Quantity Needed",
    "Unit Size",
    "Minimum Quantity",
    "Date To Purchase",
    "Supplier or Store",
    "Price Paid",
  ];
  return (
    <div className={compact ? "tableWrap compact" : "tableWrap"}>
      <table>
        <thead>
          <tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={headers.length}>Building inventory sheet from the knowledge graph...</td></tr>
          ) : rows.length ? (
            rows.map((row, index) => (
              <tr key={`${row["Medication Name"]}-${index}`}>
                {headers.map((header) => <td key={header}>{row[header] || ""}</td>)}
              </tr>
            ))
          ) : (
            <tr><td colSpan={headers.length}>No medication inventory rows were predicted for this appointment.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function VendorInvoiceTable({ rows }) {
  const headers = ["Medication Name", "Quantity", "Unit Size", "Price", "Cart Status"];
  return (
    <div className="vendorInvoiceTable">
      <table>
        <thead>
          <tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row) => (
              <tr key={`${row.Line}-${row["Medication Name"]}`}>
                {headers.map((header) => <td key={header}>{row[header] || ""}</td>)}
              </tr>
            ))
          ) : (
            <tr><td colSpan={headers.length}>No vendor invoice rows are available yet.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function EvidenceTable({ title, rows }) {
  const headers = rows[0] ? Object.keys(rows[0]) : [];
  return (
    <div className="evidencePanel">
      <h4>{title}</h4>
      <div className="tableWrap compact">
        <table>
          <thead>
            <tr>{headers.map((header) => <th key={header}>{header.replaceAll("_", " ")}</th>)}</tr>
          </thead>
          <tbody>
            {rows.length ? rows.slice(0, 60).map((row, index) => (
              <tr key={index}>
                {headers.map((header) => <td key={header}>{String(row[header] ?? "")}</td>)}
              </tr>
            )) : <tr><td>No evidence rows.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ChatWidget({ open, setOpen, messages, chatInput, setChatInput, sendMessage, busy }) {
  function sourceLabel(source) {
    if (source === "kg-fast-cache") return "KG cache";
    if (source === "kg-fast") return "KG";
    if (source === "codex") return "Codex";
    return source;
  }

  return (
    <>
      {open ? (
        <aside className="chatPanel">
          <div className="chatHeader">
            <div>
              <strong>Inventory assistant</strong>
              <span>Fast KG answers, Codex for deeper analysis</span>
            </div>
            <button onClick={() => setOpen(false)} aria-label="Close chat">x</button>
          </div>
          <div className="chatMessages">
            {messages.map((message, index) => (
              <div className={`message ${message.role}`} key={index}>
                <b>{message.role === "user" ? "You" : "Assistant"}</b>
                <p>{message.content}</p>
                {message.source ? <small>{sourceLabel(message.source)}</small> : null}
              </div>
            ))}
            {busy ? <div className="message assistant"><b>Assistant</b><p>Checking the KG inventory...</p></div> : null}
          </div>
          <form className="chatForm" onSubmit={sendMessage}>
            <input
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Quantity needed? Supplier or price? Why included?"
            />
            <button disabled={busy || !chatInput.trim()}>Ask</button>
          </form>
        </aside>
      ) : null}
      <button className="chatLauncher" onClick={() => setOpen((value) => !value)} aria-label="Open inventory chat">
        <span className="chatIcon" />
        Chat
      </button>
    </>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
