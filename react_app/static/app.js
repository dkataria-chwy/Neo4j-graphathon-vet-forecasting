const { useEffect, useMemo, useState } = React;

const emptyMetrics = {
  similarAppointments: 0,
  medications: 0,
  quantityNeeded: 0,
  kgEvidence: 0,
  chargeLines: 0,
  expectedTotalCost: 0,
  forecastVisits: 0,
  fourWeekStockItems: 0,
  database: "neo4j",
};

const defaultVendors = ["Amazon", "Chewy", "Covetrus", "MWI", "Patterson", "Med-Vet International", "Use KG supplier"];

function todayPlus(days) {
  const value = new Date();
  value.setDate(value.getDate() + days);
  return value.toISOString().slice(0, 10);
}

function money(value) {
  const number = Number(value || 0);
  if (!Number.isFinite(number)) return "$0.00";
  return number.toLocaleString("en-US", { style: "currency", currency: "USD" });
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

function fileStem(filters, payload) {
  const vendor = (filters.vendor || "vendor").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
  const period = (payload.appointmentDate || "all_future").replace(/[^a-z0-9]+/gi, "_").replace(/^_|_$/g, "");
  return `florida_plantation_inventory_${vendor}_${period}`;
}

function App() {
  const [bootstrap, setBootstrap] = useState(null);
  const [filters, setFilters] = useState({
    vendor: "Med-Vet International",
  });
  const [payload, setPayload] = useState({
    clinicName: "Florida Plantation Clinic",
    forecastOptions: [],
    inventory: [],
    vendorInvoice: [],
    chargeLines: [],
    inventoryRollup: [],
    evidenceTrail: [],
    provenance: [],
    forecastRules: [],
    metrics: emptyMetrics,
    purchaseDate: todayPlus(5),
    vendor: "Med-Vet International",
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
      content: "Ask why a medication is on the sheet, which past visits support it, or what needs to be ordered.",
    },
  ]);

  const requestFilters = useMemo(() => filters, [filters]);
  const metrics = payload.metrics || emptyMetrics;
  const vendorOptions = payload.vendorOptions || bootstrap?.vendorOptions || defaultVendors;
  const hasRows = payload.inventory?.length > 0;
  const selectedVendor = payload.vendor || filters.vendor || "Med-Vet International";
  const vendorInvoice = payload.vendorInvoice || [];
  const vendorPreview = vendorInvoice.slice(0, 3);
  const forecastCount = metrics.forecastVisits || bootstrap?.forecastOptions?.length || 0;
  const forecastPeriod = payload.appointmentDate || `${bootstrap?.minHistoryDate || ""} to ${bootstrap?.maxHistoryDate || ""}`;
  const cartStatusLabel = {
    cart_complete: "Cart complete",
    cart_partial: "Cart partially complete",
    cart_stopped: "Cart stopped",
    draft_ready: "Cart draft ready",
    manual_review: "Manual review",
  }[cartResult?.status] || "Cart update";

  async function loadBootstrap() {
    const response = await fetch("/api/bootstrap");
    if (!response.ok) throw new Error("Could not load forecast metadata.");
    const data = await response.json();
    setBootstrap(data);
    setFilters((current) => ({
      ...current,
      vendor: current.vendor || "Med-Vet International",
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
      if (!response.ok) throw new Error("Could not build the forecast charge sheet.");
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
    loadInventory(filters);
  }, [filters.vendor]);

  function updateFilter(name, value) {
    if (name === "vendor") setCartResult(null);
    setFilters((current) => ({ ...current, [name]: value }));
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
    downloadBlob(blob, `${fileStem(filters, payload)}.${type === "xlsx" ? "xlsx" : type}`);
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

  return (
    <main>
      <section className="hero">
        <div>
          <div className="eyebrow">{payload.clinicName || "Florida Plantation Clinic"}</div>
          <h1>Forecast Charge Sheet</h1>
          <p>
            Clinic-level medication inventory from all upcoming appointments, similar historical invoices, and a KG-backed why trail.
          </p>
        </div>
        <div className="heroBadge">
          <span>KG</span>
          <strong>{metrics.database || "neo4j"}</strong>
        </div>
      </section>

      <section className="controls">
        <div className="controlHeading">Forecast scope</div>
        <div className="targetGrid">
          <div className="scopeCard">
            <b>All upcoming appointments</b>
            <span>{forecastCount} forecast targets · {metrics.kgEvidence || 0} EVIDENCED_BY links · Neo4j only</span>
          </div>
          <label>
            Vendor invoice
            <select value={filters.vendor} onChange={(event) => updateFilter("vendor", event.target.value)}>
              {vendorOptions.map((vendor) => (
                <option key={vendor} value={vendor}>{vendor}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="appointmentSummary">
          <div><b>Clinic</b><span>{payload.clinicName || "Florida Plantation Clinic"}</span></div>
          <div><b>Period</b><span>{forecastPeriod || "-"}</span></div>
          <div><b>Demand</b><span>{metrics.quantityNeeded || 0} units</span></div>
          <div className="summaryWide"><b>Source</b><span>Future appointments matched to historical invoice items in Neo4j</span></div>
        </div>
      </section>

      {error ? <div className="error">{error}</div> : null}

      <section className="metrics">
        <Metric label="Upcoming appointments" value={forecastCount} detail={`${metrics.kgEvidence || 0} KG evidence links`} color="#2563eb" />
        <Metric label="Inventory rows" value={metrics.medications} detail={`${metrics.quantityNeeded || 0} units to prepare`} color="#0f766e" />
        <Metric label="Expected billing" value={money(metrics.expectedTotalCost)} detail="forecasted across schedule" color="#475569" small />
      </section>

      <section className="sheetTop">
        <div>
          <h2>Medication inventory sheet</h2>
          <p>
            {payload.clinicName} · all upcoming appointments · {selectedVendor} · purchase by {payload.purchaseDate}
          </p>
        </div>
        <span className={hasRows ? "status ready" : "status"}>{hasRows ? "Ready to export" : "No rows to export"}</span>
      </section>

      <section className="sheet">
        <div className="sheetHeader">
          <div>
            <h3>Medication Inventory Tracker</h3>
            <p>All upcoming appointments · {forecastPeriod}</p>
          </div>
          <strong>Purchase by {payload.purchaseDate}</strong>
        </div>
        <div className="metaRows">
          <div><b>Clinic</b><span>{payload.clinicName}</span></div>
          <div><b>Forecast Period</b><span>{forecastPeriod}</span></div>
          <div><b>Forecast Source</b><span>{forecastCount} upcoming appointments</span></div>
          <div><b>Vendor</b><span>{selectedVendor}</span></div>
        </div>
        <InventoryTable rows={payload.inventory || []} loading={loading} />
      </section>

      <section className="exportBar">
        <div className="exportTitle">Export inventory sheet</div>
        <div className="exportActions">
          <button disabled={!hasRows} onClick={() => exportSheet("pdf")}>PDF</button>
          <button disabled={!hasRows} onClick={() => exportSheet("xlsx")}>Excel</button>
          <button disabled={!hasRows} onClick={() => exportSheet("csv")}>CSV</button>
          <span>Exports use all upcoming appointment forecast rows and the selected vendor.</span>
        </div>
      </section>

      <section className="evidence">
        <EvidenceCards rows={payload.evidenceTrail || []} />
      </section>

      <section className="vendorPanel">
        <div className="vendorToolbar">
          <div className="vendorSelector">
            <b>{selectedVendor} invoice</b>
            <span>
              Showing {Math.min(3, vendorInvoice.length || 0)} of {vendorInvoice.length || 0} rows · {payload.vendorWebsite || "KG supplier"}
            </span>
          </div>
          <button disabled={!hasRows || cartBusy} onClick={() => createVendorCart(false, false)}>Create cart draft</button>
          <button disabled={!hasRows || cartBusy} onClick={() => createVendorCart(true, true)}>Open website and add cart</button>
        </div>
        <VendorInvoiceTable rows={vendorPreview} />
        {cartResult ? (
          <div className={`cartResult ${cartResult.status || ""}`}>
            <b>{cartStatusLabel}</b>
            <span>{cartResult.message}</span>
            {cartResult.results?.length ? (
              <div className="cartResultList">
                <span>
                  Confirmed: {cartResult.results
                    .filter((row) => String(row.status || "").startsWith("added_to_cart"))
                    .map((row) => row["Medication Name"])
                    .join(", ") || "No additions confirmed yet"}
                </span>
              </div>
            ) : null}
          </div>
        ) : null}
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

function InventoryTable({ rows, loading = false }) {
  const headers = [
    "Medication Name",
    "Product Type",
    "Quantity Needed",
    "Expected Units",
    "Unit Size",
    "Forecasted Appointments",
    "Date To Purchase",
    "Supplier or Store",
    "Expected Cost",
  ];
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>{headers.map((header) => <th key={header}>{header}</th>)}</tr>
        </thead>
        <tbody>
          {loading ? (
            <tr><td colSpan={headers.length}>Building inventory sheet from forecasted invoice lines...</td></tr>
          ) : rows.length ? (
            rows.map((row, index) => (
              <tr key={`${row["Medication Name"]}-${index}`}>
                {headers.map((header) => <td key={header}>{row[header] || ""}</td>)}
              </tr>
            ))
          ) : (
            <tr><td colSpan={headers.length}>No stockable medication rows were predicted for upcoming appointments.</td></tr>
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

function EvidenceCards({ rows }) {
  const cards = (rows || []).slice(0, 3);
  if (!cards.length) {
    return (
      <section className="evidenceCards">
        <div className="evidenceCard">
          <b>KG evidence</b>
          <p>No evidence rows are available from Neo4j.</p>
        </div>
      </section>
    );
  }
  return (
    <section className="evidenceCards">
      {cards.map((row, index) => (
        <article className="evidenceCard" key={`${row["Future Appointment"]}-${row["Past Appointment"]}-${index}`}>
          <div className="evidenceCardTop">
            <b>{row["Future Pet"] || row["Future Appointment"]}</b>
            <span>{row["Future Date"]} · similarity {row.Similarity}</span>
          </div>
          <div className="evidencePair">
            <div>
              <small>Future complaint</small>
              <p>{row["Future Complaint"] || "-"}</p>
            </div>
            <div>
              <small>Matched invoice visit</small>
              <p>{row["Past Appointment"]} · {row["Past Date"]}</p>
            </div>
          </div>
          <div className="invoiceSnippet">
            <small>Invoice evidence</small>
            <p>{row["Invoice Items"] || "-"}</p>
          </div>
        </article>
      ))}
    </section>
  );
}

function EvidenceTable({ title, rows }) {
  const headers = rows[0] ? Object.keys(rows[0]).filter((header) => !header.startsWith("_")) : [];
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
              <span>Ask why, quantity, vendor, or evidence questions</span>
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
            {busy ? <div className="message assistant"><b>Assistant</b><p>Checking forecast evidence...</p></div> : null}
          </div>
          <form className="chatForm" onSubmit={sendMessage}>
            <input
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Why is Gabapentin here?"
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
