// The floating chat, bottom-right on every page: a button with the unread total, and a
// panel that shows either the list of conversations or one conversation.
import { ArrowLeft, Eye, MessageCircle, MessagesSquare, X } from "lucide-react";
import { useChat } from "../chat";
import { STATUS, formatDateTime } from "../format";
import ChatThread from "./ChatThread";

export default function ChatDock() {
  const { open, setOpen, activeId, setActiveId, chats, totalUnread } = useChat();
  const active = chats.find((c) => c.request_id === activeId);

  return (
    <>
      {open && (
        <section className="chat-dock" role="dialog" aria-label="Chat">
          <header className="chat-dock-head">
            {activeId ? (
              <>
                <button className="icon-btn" onClick={() => setActiveId(null)} aria-label="All conversations">
                  <ArrowLeft size={16} />
                </button>
                <div className="who">
                  <div className="t">#{activeId} · {active?.task_name ?? "Conversation"}</div>
                  {active && (
                    <div className="s">
                      {active.client_name}
                      {active.operator_name ? ` · operator ${active.operator_name}` : " · no operator yet"}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="who">
                <div className="t">Messages</div>
                <div className="s">{totalUnread ? `${totalUnread} unread` : "All caught up"}</div>
              </div>
            )}
            <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Close chat">
              <X size={16} />
            </button>
          </header>

          {activeId ? (
            <ChatThread key={activeId} requestId={activeId} canWrite={active ? active.can_write : true} />
          ) : (
            <ConversationList chats={chats} onPick={setActiveId} />
          )}
        </section>
      )}

      <button
        className={`chat-launcher ${open ? "is-open" : ""}`}
        onClick={() => setOpen(!open)}
        aria-label={open ? "Close chat" : `Open chat${totalUnread ? `, ${totalUnread} unread` : ""}`}
      >
        {open ? <X size={22} /> : <MessageCircle size={22} />}
        {!open && totalUnread > 0 && <span className="launcher-count">{totalUnread > 99 ? "99+" : totalUnread}</span>}
      </button>
    </>
  );
}

function ConversationList({ chats, onPick }) {
  if (chats.length === 0) {
    return (
      <div className="chat-dock-empty">
        <MessagesSquare size={28} aria-hidden="true" />
        <p>No conversations yet. They appear here for requests you are part of.</p>
      </div>
    );
  }
  return (
    <ul className="chat-list-items">
      {chats.map((c) => (
        <li key={c.request_id}>
          <button className={`chat-item ${c.unread ? "unread" : ""}`} onClick={() => onPick(c.request_id)}>
            <span className={`chat-item-dot tone-${STATUS[c.status].tone}`} aria-hidden="true">#{c.request_id}</span>
            <span className="chat-item-body">
              <span className="chat-item-top">
                <strong>{c.task_name}</strong>
                {c.last_at && <span className="time">{formatDateTime(c.last_at)}</span>}
              </span>
              <span className="chat-item-last">
                {c.last_body ? `${c.last_author}: ${c.last_body}` : `${c.client_name} · no messages yet`}
              </span>
            </span>
            {c.unread > 0 ? (
              <span className="unread-badge">{c.unread}</span>
            ) : (
              !c.can_write && <Eye size={14} className="muted" aria-label="Read only" />
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
