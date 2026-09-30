// One conversation. New messages arrive by asking the server every few seconds for anything
// newer than the last one we have (?after_id=...). What you see is marked as read.
import { Eye, Send } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { useChat } from "../chat";
import { formatDateTime } from "../format";
import { useToast } from "../toast";

const POLL_MS = 4000;

export default function ChatThread({ requestId, canWrite }) {
  const { user } = useAuth();
  const { refresh: refreshList } = useChat();
  const toast = useToast();
  const [messages, setMessages] = useState([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(null);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const lastId = useRef(0);
  const listRef = useRef(null);

  // Tell the server how far we have read, then refresh the unread badges.
  const markRead = useCallback(
    (id) =>
      api(`/requests/${requestId}/messages/read`, { method: "POST", body: { last_read_id: id } })
        .then(refreshList)
        .catch(() => {}),
    [requestId, refreshList],
  );

  // Add messages we have not seen yet (the same one can come from polling AND sending).
  const add = useCallback((incoming) => {
    if (incoming.length === 0) return false;
    setMessages((current) => {
      const known = new Set(current.map((m) => m.id));
      return [...current, ...incoming.filter((m) => !known.has(m.id))];
    });
    lastId.current = Math.max(lastId.current, ...incoming.map((m) => m.id));
    return true;
  }, []);

  useEffect(() => {
    let stopped = false;
    const fetchNew = () =>
      api(`/requests/${requestId}/messages?after_id=${lastId.current}`)
        .then((fresh) => {
          if (stopped) return;
          if (add(fresh)) markRead(lastId.current);
          setError(null);
        })
        .catch((err) => !stopped && setError(err))
        .finally(() => !stopped && setLoaded(true));

    fetchNew();
    const timer = setInterval(() => !document.hidden && fetchNew(), POLL_MS);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [requestId, add, markRead]);

  // Keep the newest message in view.
  useEffect(() => {
    if (listRef.current) listRef.current.scrollTop = listRef.current.scrollHeight;
  }, [messages.length]);

  async function send(e) {
    e?.preventDefault();
    if (!text.trim() || sending) return;
    setSending(true);
    try {
      const message = await api(`/requests/${requestId}/messages`, { method: "POST", body: { body: text } });
      add([message]);
      setText("");
      refreshList();
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSending(false);
    }
  }

  if (error?.status === 403) {
    return (
      <div className="chat-dock-empty">
        <Eye size={26} aria-hidden="true" />
        <p>{error.message}</p>
      </div>
    );
  }

  return (
    <>
      <div className="chat-list" ref={listRef} aria-live="polite">
        {!loaded ? (
          <div className="skeleton" style={{ height: 60 }} />
        ) : messages.length === 0 ? (
          <p className="chat-empty">No messages yet. Say hello.</p>
        ) : (
          messages.map((m) => {
            const mine = m.author_id === user.id;
            return (
              <div key={m.id} className={`msg ${mine ? "mine" : ""}`}>
                <div className="msg-meta">
                  <strong>{mine ? "You" : m.author_name}</strong>
                  {!mine && <span className={`badge ${m.author_role === "client" ? "tone-blue" : "tone-violet"}`}>{m.author_role}</span>}
                  <span>{formatDateTime(m.created_at)}</span>
                </div>
                <div className="bubble">{m.body}</div>
              </div>
            );
          })
        )}
      </div>
      {canWrite ? (
        <form className="chat-form" onSubmit={send}>
          <label className="sr-only" htmlFor={`chat-input-${requestId}`}>Message</label>
          <textarea
            id={`chat-input-${requestId}`}
            className="textarea"
            placeholder="Write a message… (Enter to send)"
            value={text}
            maxLength={2000}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send(e)}
          />
          <button className="btn btn-primary" type="submit" disabled={!text.trim() || sending} aria-label="Send">
            <Send size={15} aria-hidden="true" />
          </button>
        </form>
      ) : (
        <div className="chat-readonly">
          <Eye size={14} aria-hidden="true" /> Read only: only the client and the operators who assigned episodes can reply.
        </div>
      )}
    </>
  );
}
