import { useEffect, useMemo, useState } from "react"
import {
  UNAUTHORIZED_EVENT,
  checkSession,
  getTickets,
  login as loginRequest,
  logout as logoutRequest,
  syncEmails,
} from "./api"
import TicketCard from "./components/TicketCard"
import "./style.css"

const STATUS_FILTERS = [
  { id: "all", label: "All" },
  { id: "pending", label: "Pending" },
  { id: "edited", label: "Edited" },
  { id: "resolved", label: "Resolved" },
]

export default function App() {
  const [inboxTickets, setInboxTickets] = useState([])
  const [sentTickets, setSentTickets] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isSyncing, setIsSyncing] = useState(false)
  const [isLoggingOut, setIsLoggingOut] = useState(false)
  const [selectedStatus, setSelectedStatus] = useState("all")
  const [searchTerm, setSearchTerm] = useState("")
  const [lastUpdated, setLastUpdated] = useState(null)
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isBootstrapping, setIsBootstrapping] = useState(true)
  const [authError, setAuthError] = useState("")
  const [authLoading, setAuthLoading] = useState(false)

  const clearSessionData = () => {
    setInboxTickets([])
    setSentTickets([])
    setLastUpdated(null)
    setIsLoading(false)
    setAuthError("")
  }

  const loadTickets = async () => {
    if (!isAuthenticated) {
      setIsLoading(false)
      return
    }
    setIsLoading(true)
    try {
      const res = await getTickets()
      const inbox = res.data?.inbox ?? []
      const sent = res.data?.sent ?? []
      setInboxTickets(inbox)
      setSentTickets(sent)
      setLastUpdated(new Date())
    } catch (error) {
      if (error.response?.status === 401) {
        setIsAuthenticated(false)
        clearSessionData()
      } else {
        console.error("Failed to load tickets", error)
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleSync = async () => {
    setIsSyncing(true)
    try {
      await syncEmails()
      await loadTickets()
    } catch (error) {
      console.error("Failed to sync inbox", error)
    } finally {
      setIsSyncing(false)
    }
  }

  const handleLogin = async ({ username, password }) => {
    setAuthLoading(true)
    setAuthError("")
    try {
      await loginRequest(username, password)
      setIsAuthenticated(true)
    } catch (error) {
      console.error("Failed to login", error)
      setAuthError("Invalid username or password")
    } finally {
      setAuthLoading(false)
    }
  }

  const handleLogout = async () => {
    setIsLoggingOut(true)
    try {
      await logoutRequest()
    } catch (error) {
      console.error("Failed to logout", error)
    } finally {
      setIsLoggingOut(false)
      setIsAuthenticated(false)
      clearSessionData()
      setIsBootstrapping(false)
    }
  }

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const res = await checkSession()
        if (res.data?.authenticated) {
          setIsAuthenticated(true)
        } else {
          setIsAuthenticated(false)
          clearSessionData()
        }
      } catch (error) {
        console.error("Session check failed", error)
        setIsAuthenticated(false)
        clearSessionData()
      } finally {
        setIsBootstrapping(false)
      }
    }

    bootstrap()
  }, [])

  useEffect(() => {
    const handleUnauthorized = () => {
      setIsAuthenticated(false)
      clearSessionData()
      setIsBootstrapping(false)
    }

    if (typeof window === "undefined") return undefined
    window.addEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
    return () =>
      window.removeEventListener(UNAUTHORIZED_EVENT, handleUnauthorized)
  }, [])

  useEffect(() => {
    if (isAuthenticated) {
      loadTickets()
    }
  }, [isAuthenticated])

  const stats = useMemo(() => {
    const combined = [...inboxTickets, ...sentTickets]
    const total = combined.length
    const pending = combined.filter((t) => t.status === "pending").length
    const edited = combined.filter((t) => t.status === "edited").length
    const resolved = combined.filter((t) => t.status === "resolved").length

    return { total, pending, edited, resolved }
  }, [inboxTickets, sentTickets])

  const normalizedSearch = searchTerm.trim().toLowerCase()

  const filterTickets = (collection) =>
    collection
      .filter((ticket) => {
        const matchStatus =
          selectedStatus === "all" || ticket.status === selectedStatus
        const haystack = [
          ticket.subject,
          ticket.name,
          ticket.email,
          ticket.message,
        ]
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
        const matchSearch = haystack.includes(normalizedSearch)
        return matchStatus && matchSearch
      })
      .sort((a, b) => Number(a.id ?? 0) - Number(b.id ?? 0))

  const filteredInbox = useMemo(
    () => filterTickets(inboxTickets),
    [inboxTickets, normalizedSearch, selectedStatus],
  )

  const filteredSent = useMemo(
    () => filterTickets(sentTickets),
    [sentTickets, normalizedSearch, selectedStatus],
  )

  const lastUpdatedLabel = lastUpdated
    ? lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "--"

  if (isBootstrapping) {
    return (
      <div className="login-page">
        <div className="login-card">
          <p className="eyebrow">AI Customer Desk</p>
          <h1>Checking session…</h1>
          <p className="hero-subtitle">
            Hold on while we verify your admin session.
          </p>
        </div>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="login-page">
        <LoginPanel onSubmit={handleLogin} loading={authLoading} error={authError} />
      </div>
    )
  }

  return (
    <div className="page">
      <header className="hero">
        <div>
          <p className="eyebrow">AI Customer Desk</p>
          <h1>📨 Support Control Center</h1>
          <p className="hero-subtitle">
            Monitor inbox health, edit AI replies, and keep response time razor sharp.
          </p>
        </div>
        <div className="hero-meta">
          <span>Last sync • {lastUpdatedLabel}</span>
          <div className="hero-actions">
            <button
              className="primary"
              onClick={handleSync}
              disabled={isSyncing}
            >
              {isSyncing ? "Syncing…" : "Sync Inbox"}
            </button>
            <button onClick={loadTickets} disabled={isLoading}>
              {isLoading ? "Refreshing…" : "Refresh"}
            </button>
            <button className="ghost" onClick={handleLogout} disabled={isLoggingOut}>
              {isLoggingOut ? "Logging out…" : "Logout"}
            </button>
          </div>
        </div>
      </header>

      <section className="stat-grid">
        <article className="stat-card">
          <p>Total tickets</p>
          <strong>{stats.total}</strong>
        </article>
        <article className="stat-card">
          <p>Pending</p>
          <strong>{stats.pending}</strong>
        </article>
        <article className="stat-card">
          <p>Edited</p>
          <strong>{stats.edited}</strong>
        </article>
        <article className="stat-card">
          <p>Resolved</p>
          <strong>{stats.resolved}</strong>
        </article>
      </section>

      <section className="controls">
        <div className="search">
          <input
            type="search"
            placeholder="Search subject, customer, or email"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <div className="status-pills">
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.id}
              className={selectedStatus === filter.id ? "active" : ""}
              onClick={() => setSelectedStatus(filter.id)}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </section>

      <section className="ticket-section">
        <div className="section-header">
          <div>
            <p className="section-eyebrow">Open queue</p>
            <h2>Inbox Tickets</h2>
            <p className="section-subtitle">
              Conversations that still need a human review before sending.
            </p>
          </div>
          <span>{filteredInbox.length} visible</span>
        </div>

        <div className="ticket-grid">
          {isLoading && (
            <div className="empty-state">
              <h3>Loading inbox</h3>
              <p>Pulling the latest conversations from the inbox…</p>
            </div>
          )}

          {!isLoading && filteredInbox.length === 0 && (
            <div className="empty-state">
              <h3>No inbox tickets match</h3>
              <p>Adjust the filters or clear the search query.</p>
            </div>
          )}

          {!isLoading &&
            filteredInbox.map((ticket) => (
              <TicketCard key={ticket.id} ticket={ticket} refresh={loadTickets} />
            ))}
        </div>
      </section>

      <section className="ticket-section">
        <div className="section-header">
          <div>
            <p className="section-eyebrow">Delivered responses</p>
            <h2>Sent Replies</h2>
            <p className="section-subtitle">
              AI-assisted replies that already went out to customers.
            </p>
          </div>
          <span>{filteredSent.length} visible</span>
        </div>

        <div className="ticket-grid">
          {isLoading && (
            <div className="empty-state">
              <h3>Syncing sent mail</h3>
              <p>Gathering the latest resolved conversations…</p>
            </div>
          )}

          {!isLoading && filteredSent.length === 0 && (
            <div className="empty-state">
              <h3>No sent replies match</h3>
              <p>Try showing resolved tickets or clearing search filters.</p>
            </div>
          )}

          {!isLoading &&
            filteredSent.map((ticket) => (
              <TicketCard
                key={`sent-${ticket.id}`}
                ticket={ticket}
                refresh={loadTickets}
                readOnly
              />
            ))}
        </div>
      </section>
    </div>
  )
}

function LoginPanel({ onSubmit, loading, error }) {
  const [username, setUsername] = useState("admin")
  const [password, setPassword] = useState("")

  const handleSubmit = (event) => {
    event.preventDefault()
    onSubmit({ username, password })
  }

  return (
    <div className="login-card">
      <p className="eyebrow">AI Customer Desk</p>
      <h1>Sign in to Support Dashboard</h1>
      <p className="hero-subtitle">
        Use the shared admin credentials to unlock the internal console.
      </p>
      <form className="login-form" onSubmit={handleSubmit}>
        <label>
          Username
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error && <p className="login-error">{error}</p>}
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Enter Dashboard"}
        </button>
      </form>
    </div>
  )
}
