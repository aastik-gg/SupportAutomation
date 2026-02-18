import { useEffect, useState } from "react"
import { sendReply, updateReply } from "../api"

export default function TicketCard({ ticket, refresh, readOnly = false }) {
  const [reply, setReply] = useState(ticket.ai_reply || "")
  const [isSaving, setIsSaving] = useState(false)
  const [isSending, setIsSending] = useState(false)

  useEffect(() => {
    setReply(ticket.ai_reply || "")
  }, [ticket.id, ticket.ai_reply])

  const handleSend = async () => {
    if (isSending) return
    setIsSending(true)
    try {
      await updateReply(ticket.id, reply)
      await sendReply(ticket.id)
      refresh?.()
    } catch (error) {
      console.error("Failed to send reply", error)
      if (typeof window !== "undefined") {
        window.alert(
          "Unable to send reply. Please review the draft, save it, and try again.",
        )
      }
    } finally {
      setIsSending(false)
    }
  }

  const handleSave = async () => {
    if (isSaving) return
    setIsSaving(true)
    try {
      await updateReply(ticket.id, reply)
      refresh?.()
    } catch (error) {
      console.error("Failed to save reply", error)
    } finally {
      setIsSaving(false)
    }
  }

  const status = ticket.status || "pending"
  const ticketId = ticket.id ?? "--"

  return (
    <article className={`ticket-card${readOnly ? " is-resolved" : ""}`}>
      <div className="ticket-head">
        <div>
          <p className="ticket-id">#{ticketId}</p>
          <h3>{ticket.subject || "No subject"}</h3>
          <p className="ticket-meta">
            {ticket.name || "Unknown customer"}
            {ticket.email && <span> • {ticket.email}</span>}
          </p>
        </div>
        <span className={`status-badge ${status}`}>{status}</span>
      </div>

      <p className="ticket-body">
        {ticket.message || "No message provided."}
      </p>

      {!readOnly ? (
        <>
          <label className="textarea-label" htmlFor={`reply-${ticketId}`}>
            AI Reply Draft
          </label>
          <textarea
            id={`reply-${ticketId}`}
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            placeholder="Tweak the AI generated response before sending"
          />

          <div className="ticket-actions">
            <button className="ghost" onClick={handleSave} disabled={isSaving}>
              {isSaving ? "Saving…" : "Save Edit"}
            </button>
            <button className="accent" onClick={handleSend} disabled={isSending}>
              {isSending ? "Sending…" : "Send Reply"}
            </button>
          </div>
        </>
      ) : (
        <div className="reply-preview">
          <p className="textarea-label">Sent Reply</p>
          <p>{ticket.ai_reply || "Reply not stored."}</p>
        </div>
      )}
    </article>
  )
}
