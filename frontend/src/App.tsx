import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./App.css";

type Metrics = {
  mae_mw: number | null;
  rmse_mw: number | null;
  bias_mw: number | null;
};

type Coverage = {
  total_hours: number;
  matched_hours: number;
  missing_forecast_hours: number;
  missing_actual_hours: number;
};

type Interval = {
  delivery_time: string;
  publish_time: string | null;
  forecast_mw: number | null;
  actual_mw: number | null;
  error_mw: number | null;
  status: "matched" | "missing_forecast" | "missing_actuals";
};

type Analysis = {
  metrics: Metrics;
  coverage: Coverage;
  intervals: Interval[];
};

type Query = {
  startDate: string;
  endDate: string;
  leadHours: number;
};

type StatusFilter = "all" | Interval["status"];

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ??
  (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/+$/, "");

const DEFAULT_QUERY: Query = {
  startDate: "2026-01-01",
  endDate: "2026-01-31",
  leadHours: 24,
};

async function fetchAnalysis(
  query: Query,
  signal: AbortSignal,
): Promise<Analysis> {
  const params = new URLSearchParams({
    start_date: query.startDate,
    end_date: query.endDate,
    decision_lead_hours: String(query.leadHours),
  });

  const response = await fetch(
    `${API_BASE_URL}/api/v1/analysis?${params.toString()}`,
    { signal },
  );

  if (!response.ok) {
    let message = `Analysis request failed (${response.status})`;

    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      message = `Analysis request failed (${response.status})`;
    }

    throw new Error(message);
  }

  return (await response.json()) as Analysis;
}

function formatNumber(value: number | null, decimals = 1): string {
  if (value === null || !Number.isFinite(value)) return "?€”";

  return value.toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatTimestamp(value: string | null): string {
  if (!value) return "Unavailable";

  return new Date(value).toLocaleString("en-GB", {
    timeZone: "UTC",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZoneName: "short",
  });
}

function shortTimestamp(value: string): string {
  return new Date(value).toLocaleString("en-GB", {
    timeZone: "UTC",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    hour12: false,
  });
}

function App() {
  const [formQuery, setFormQuery] = useState<Query>(DEFAULT_QUERY);
  const [appliedQuery, setAppliedQuery] = useState<Query>(DEFAULT_QUERY);
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAllRows, setShowAllRows] = useState(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [pageSize, setPageSize] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    const controller = new AbortController();

    fetchAnalysis(appliedQuery, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        setAnalysis(result);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (
          controller.signal.aborted ||
          (cause instanceof Error && cause.name === "AbortError")
        ) {
          return;
        }

        setError(
          cause instanceof Error
            ? cause.message
            : "An unexpected error occurred.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [appliedQuery]);

  const chartData = useMemo(
    () =>
      (analysis?.intervals ?? []).map((interval) => ({
        ...interval,
        timeLabel: shortTimestamp(interval.delivery_time),
      })),
    [analysis],
  );

  const largestErrors = useMemo(
    () =>
      [...chartData]
        .filter(
          (interval) =>
            interval.error_mw !== null &&
            Number.isFinite(interval.error_mw),
        )
        .sort(
          (a, b) =>
            Math.abs(b.error_mw ?? 0) - Math.abs(a.error_mw ?? 0),
        )
        .slice(0, 8),
    [chartData],
  );

  const filteredRows = useMemo(() => {
    const rows = showAllRows ? chartData : largestErrors;

    if (!showAllRows || statusFilter === "all") {
      return rows;
    }

    return rows.filter((interval) => interval.status === statusFilter);
  }, [showAllRows, chartData, largestErrors, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredRows.length / pageSize));
  const safeCurrentPage = Math.min(currentPage, totalPages);

  const tableRows = showAllRows
    ? filteredRows.slice(
        (safeCurrentPage - 1) * pageSize,
        safeCurrentPage * pageSize,
      )
    : filteredRows;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (formQuery.endDate < formQuery.startDate) {
      setError("End date must be on or after start date.");
      return;
    }

    setLoading(true);
    setError(null);
    setAnalysis(null);
    setShowAllRows(false);
    setStatusFilter("all");
    setPageSize(25);
    setCurrentPage(1);
    setAppliedQuery({ ...formQuery });
  }

  function retryAnalysis() {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    setAppliedQuery({ ...appliedQuery });
  }

  const metrics = analysis?.metrics;
  const coverage = analysis?.coverage;

  const coveragePercent =
    coverage && coverage.total_hours > 0
      ? (coverage.matched_hours / coverage.total_hours) * 100
      : 0;

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">W</span>
          <span>WINDINSIGHT</span>
        </div>

        <div className="topbar-right">
          <span className="live-indicator">
            <i className="status-dot" />
            Elexon data analysis
          </span>
          <span className="topbar-divider" />
          <span className="topbar-period">
            {appliedQuery.startDate === appliedQuery.endDate
              ? appliedQuery.startDate
              : `${appliedQuery.startDate} ?€” ${appliedQuery.endDate}`}
          </span>
        </div>
      </header>

      <section className="page-intro">
        <div>
          <p className="eyebrow">UK ENERGY MARKET | ANALYTICS</p>
          <h1>Wind forecast accuracy</h1>
          <p className="intro-copy">
            Compare forecast wind generation with actual output to understand
            forecast errors, data coverage and potential signals for energy
            purchasing decisions.
          </p>
        </div>

        <div className="period-chip">
          <span className="period-icon">TIME</span>
          <span>Decision lead: {appliedQuery.leadHours} hours</span>
        </div>
      </section>

      <section className="filter-panel" aria-label="Analysis controls">
        <form className="filter-form" onSubmit={handleSubmit}>
          <label>
            <span>START DATE</span>
            <input
              type="date"
              value={formQuery.startDate}
              max={formQuery.endDate}
              required
              onChange={(event) =>
                setFormQuery((current) => ({
                  ...current,
                  startDate: event.target.value,
                }))
              }
            />
          </label>

          <label>
            <span>END DATE</span>
            <input
              type="date"
              value={formQuery.endDate}
              min={formQuery.startDate}
              required
              onChange={(event) =>
                setFormQuery((current) => ({
                  ...current,
                  endDate: event.target.value,
                }))
              }
            />
          </label>

          <label>
            <span>DECISION LEAD TIME</span>
            <select
              value={formQuery.leadHours}
              onChange={(event) =>
                setFormQuery((current) => ({
                  ...current,
                  leadHours: Number(event.target.value),
                }))
              }
            >
              {[0, 6, 12, 24, 36, 48, 72, 96, 120, 168].map((hours) => (
                <option key={hours} value={hours}>
                  {hours} hours
                </option>
              ))}
            </select>
          </label>

          <button
            className="primary-button"
            type="submit"
            disabled={loading}
          >
            {loading ? "Analysing..." : "Run analysis"} <span>&gt;</span>
          </button>
        </form>

        <p className="filter-note">
          Forecast selection uses the latest available publication at or before
          the delivery time minus the selected decision lead. Times are UTC.
          The lead time is a configurable analytical assumption.
        </p>
      </section>

      {error && (
        <section className="error-banner" role="alert">
          <span className="error-symbol">!</span>
          <p>{error}</p>
          <button
            type="button"
            className="retry-button"
            onClick={retryAnalysis}
            disabled={loading}
          >
            Retry
          </button>
        </section>
      )}

      {loading && (
        <section className="loading-panel" aria-live="polite">
          <span className="loading-spinner" />
          Loading wind generation data and calculating accuracy?€¦
        </section>
      )}

      {!loading && !error && analysis && (
        <>
          <section className="metrics-grid" aria-label="Forecast metrics">
            <article className="metric-card metric-primary">
              <div className="metric-top">
                <span className="metric-label">Mean absolute error</span>
                <span className="metric-symbol">MAE</span>
              </div>
              <div className="metric-value">
                {formatNumber(metrics?.mae_mw ?? null)} MW
              </div>
              <p className="metric-description">
                Average magnitude of forecast error. Lower is better.
              </p>
              <div className="metric-footer">
                <i className="metric-footer-dot" />
                Across matched intervals
              </div>
            </article>

            <article className="metric-card">
              <div className="metric-top">
                <span className="metric-label">Root mean square error</span>
                <span className="metric-symbol">RMSE</span>
              </div>
              <div className="metric-value">
                {formatNumber(metrics?.rmse_mw ?? null)} MW
              </div>
              <p className="metric-description">
                Gives larger forecast misses more weight.
              </p>
              <div className="metric-footer">
                <i className="metric-footer-dot" />
                Error magnitude
              </div>
            </article>

            <article className="metric-card">
              <div className="metric-top">
                <span className="metric-label">Forecast bias</span>
                <span className="metric-symbol">+/-</span>
              </div>
              <div className="metric-value">
                {metrics?.bias_mw !== null &&
                metrics?.bias_mw !== undefined &&
                metrics.bias_mw > 0
                  ? "+"
                  : ""}
                {formatNumber(metrics?.bias_mw ?? null)} MW
              </div>
              <p className="metric-description">
                Positive means overforecasting; negative means underforecasting.
              </p>
              <div className="metric-footer">
                <i className="metric-footer-dot" />
                Mean signed error
              </div>
            </article>

            <article className="metric-card">
              <div className="metric-top">
                <span className="metric-label">Data coverage</span>
                <span className="metric-symbol">OK</span>
              </div>
              <div className="metric-value">{coveragePercent.toFixed(1)}%</div>
              <p className="metric-description">
                {coverage?.matched_hours ?? 0} of {coverage?.total_hours ?? 0}{" "}
                hours matched
              </p>
              <div className="coverage-track">
                <span style={{ width: `${coveragePercent}%` }} />
              </div>
            </article>
          </section>

          <section className="chart-panel">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">GENERATION PROFILE</p>
                <h2>Forecast vs actual</h2>
                <p className="panel-subtitle">
                  Hourly wind generation | megawatts
                </p>
              </div>
              <span className="unit-chip">MW</span>
            </div>

            <div className="chart-legend">
              <span>
                <i className="legend-dot forecast-dot" /> Forecast
              </span>
              <span>
                <i className="legend-dot actual-dot" /> Actual generation
              </span>
            </div>

            <div className="main-chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={chartData}
                  margin={{ top: 12, right: 18, bottom: 4, left: 4 }}
                >
                  <CartesianGrid
                    stroke="#e9edf2"
                    strokeDasharray="3 5"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="timeLabel"
                    tick={{ fill: "#7b8798", fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    minTickGap={55}
                  />
                  <YAxis
                    width={65}
                    tick={{ fill: "#7b8798", fontSize: 11 }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={(value: number) =>
                      value.toLocaleString("en-GB")
                    }
                  />
                  <Tooltip
                    labelFormatter={(_, payload) => {
                      const point = payload?.[0]?.payload as
                        | Interval
                        | undefined;
                      return point?.delivery_time
                        ? formatTimestamp(point.delivery_time)
                        : "";
                    }}
                    formatter={(value, name) => [
                      `${formatNumber(value == null ? null : Number(value))} MW`,
                      name === "forecast_mw" ? "Forecast" : "Actual generation",
                    ]}
                    contentStyle={{
                      border: "1px solid #e3e8ef",
                      borderRadius: 10,
                      fontSize: 12,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="forecast_mw"
                    name="forecast_mw"
                    stroke="#3978e8"
                    strokeWidth={1.7}
                    dot={false}
                    connectNulls={false}
                    activeDot={{ r: 4 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="actual_mw"
                    name="actual_mw"
                    stroke="#10a47a"
                    strokeWidth={1.7}
                    dot={false}
                    connectNulls={false}
                    activeDot={{ r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>

            <p className="chart-footnote">
              Actual hourly values are calculated from the two corresponding
              half-hourly observations. Incomplete pairs remain missing.
            </p>
          </section>

          <section className="lower-grid">
            <article className="chart-panel error-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">ERROR SIGNAL</p>
                  <h2>Hourly forecast error</h2>
                  <p className="panel-subtitle">
                    Positive values indicate overforecasting
                  </p>
                </div>
              </div>

              <div className="error-chart">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={chartData}
                    margin={{ top: 12, right: 12, bottom: 4, left: 0 }}
                  >
                    <CartesianGrid
                      stroke="#e9edf2"
                      strokeDasharray="3 5"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="timeLabel"
                      tick={{ fill: "#7b8798", fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                      minTickGap={60}
                    />
                    <YAxis
                      width={58}
                      tick={{ fill: "#7b8798", fontSize: 10 }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <ReferenceLine
                      y={0}
                      stroke="#8d98a8"
                      strokeDasharray="4 4"
                    />
                    <Tooltip
                      labelFormatter={(_, payload) => {
                        const point = payload?.[0]?.payload as
                          | Interval
                          | undefined;
                        return point?.delivery_time
                          ? formatTimestamp(point.delivery_time)
                          : "";
                      }}
                      formatter={(value) => [
                        `${formatNumber(value == null ? null : Number(value))} MW`,
                        "Forecast error",
                      ]}
                      contentStyle={{
                        border: "1px solid #e3e8ef",
                        borderRadius: 10,
                        fontSize: 12,
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="error_mw"
                      name="error_mw"
                      stroke="#d97745"
                      strokeWidth={1.5}
                      dot={false}
                      connectNulls={false}
                      activeDot={{ r: 4 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="chart-panel coverage-panel">
              <div className="panel-heading">
                <div>
                  <p className="eyebrow">DATA QUALITY</p>
                  <h2>Coverage summary</h2>
                  <p className="panel-subtitle">
                    Completeness of the selected period
                  </p>
                </div>
              </div>

              <div className="coverage-summary">
                <div className="coverage-number">
                  <strong>{coverage?.matched_hours ?? 0}</strong>
                  <span>matched hours</span>
                </div>
                <div className="coverage-track coverage-track-large">
                  <span style={{ width: `${coveragePercent}%` }} />
                </div>
                <div className="coverage-row">
                  <span>
                    <i className="coverage-dot dot-green" />
                    Matched
                  </span>
                  <strong>{coverage?.matched_hours ?? 0}</strong>
                </div>
                <div className="coverage-row">
                  <span>
                    <i className="coverage-dot dot-orange" />
                    Missing forecast
                  </span>
                  <strong>{coverage?.missing_forecast_hours ?? 0}</strong>
                </div>
                <div className="coverage-row">
                  <span>
                    <i className="coverage-dot dot-grey" />
                    Missing actuals
                  </span>
                  <strong>{coverage?.missing_actual_hours ?? 0}</strong>
                </div>
                <p className="coverage-note">
                  Missing forecast and missing actual counts are independent;
                  an hour can be missing both.
                </p>
              </div>
            </article>
          </section>

          <section className="table-panel">
            <div className="panel-heading table-heading">
              <div>
                <p className="eyebrow">INTERVAL EXPLORER</p>
                <h2>
                  {showAllRows
                    ? "All hourly intervals"
                    : "Largest forecast misses"}
                </h2>
                <p className="panel-subtitle">
                  {showAllRows
                    ? `${chartData.length} hourly intervals in the selected period`
                    : "Ranked by absolute error, largest first"}
                </p>
              </div>
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setShowAllRows((current) => !current);
                  setStatusFilter("all");
                  setCurrentPage(1);
                }}
              >
                {showAllRows ? "Show largest misses" : "View all intervals"}
              </button>
            </div>

            {showAllRows && (
              <div className="interval-controls">
                <label>
                  Status
                  <select
                    value={statusFilter}
                    onChange={(event) => {
                      setStatusFilter(event.target.value as StatusFilter);
                      setCurrentPage(1);
                    }}
                  >
                    <option value="all">All statuses</option>
                    <option value="matched">Matched</option>
                    <option value="missing_forecast">Missing forecast</option>
                    <option value="missing_actuals">Missing actuals</option>
                  </select>
                </label>

                <label>
                  Rows per page
                  <select
                    value={pageSize}
                    onChange={(event) => {
                      setPageSize(Number(event.target.value));
                      setCurrentPage(1);
                    }}
                  >
                    <option value={25}>25</option>
                    <option value={50}>50</option>
                    <option value={100}>100</option>
                  </select>
                </label>

                <p className="interval-count">
                  {filteredRows.length === 0
                    ? "No intervals found"
                    : `Showing ${(safeCurrentPage - 1) * pageSize + 1}?€“${Math.min(
                        safeCurrentPage * pageSize,
                        filteredRows.length,
                      )} of ${filteredRows.length} intervals`}
                </p>

                <div className="pagination-controls">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={safeCurrentPage === 1}
                    onClick={() =>
                      setCurrentPage((page) => Math.max(1, page - 1))
                    }
                  >
                    Previous
                  </button>

                  <span>
                    Page {safeCurrentPage} of {totalPages}
                  </span>

                  <button
                    type="button"
                    className="secondary-button"
                    disabled={safeCurrentPage >= totalPages}
                    onClick={() =>
                      setCurrentPage((page) =>
                        Math.min(totalPages, page + 1),
                      )
                    }
                  >
                    Next
                  </button>
                </div>
              </div>
            )}

            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>DELIVERY TIME (UTC)</th>
                    <th>PUBLISH TIME (UTC)</th>
                    <th>FORECAST (MW)</th>
                    <th>ACTUAL (MW)</th>
                    <th>ERROR (MW)</th>
                    <th>STATUS</th>
                  </tr>
                </thead>
                <tbody>
                  {tableRows.length === 0 ? (
                    <tr>
                      <td colSpan={6}>
                        No intervals match the selected status.
                      </td>
                    </tr>
                  ) : (
                    tableRows.map((interval) => (
                      <tr key={interval.delivery_time}>
                        <td>{formatTimestamp(interval.delivery_time)}</td>
                        <td>{formatTimestamp(interval.publish_time)}</td>
                        <td>{formatNumber(interval.forecast_mw)}</td>
                        <td>{formatNumber(interval.actual_mw)}</td>
                        <td
                          className={
                            interval.error_mw === null
                              ? ""
                              : interval.error_mw > 0
                                ? "positive-error"
                                : interval.error_mw < 0
                                  ? "negative-error"
                                  : ""
                          }
                        >
                          {interval.error_mw !== null &&
                          interval.error_mw > 0
                            ? "+"
                            : ""}
                          {formatNumber(interval.error_mw)}
                        </td>
                        <td>
                          <span
                            className={`status-pill status-${interval.status}`}
                          >
                            {interval.status.replaceAll("_", " ")}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}

      <footer className="page-footer">
        <div>
          <strong>
            WIND<span>INSIGHT</span>
          </strong>
          <p>UK wind generation forecast performance</p>
        </div>
        <p>Source: Elexon BMRS | FUELHH / WINDFOR | All timestamps UTC</p>
      </footer>
    </main>
  );
}

export default App;

