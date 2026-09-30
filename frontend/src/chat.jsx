// Shared chat state for the floating chat: which conversation is open, and the list of
// conversations with unread counts. Any page can call useChat().openChat(requestId).
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api";

const ChatContext = createContext(null);
const LIST_POLL_MS = 8000;

export function ChatProvider({ children }) {
  const [open, setOpen] = useState(false);
  const [activeId, setActiveId] = useState(null); // null = show the list of conversations
  const [chats, setChats] = useState([]);

  const refresh = useCallback(() => {
    api("/chats").then(setChats).catch(() => {}); // a missed refresh is fine: the next one catches up
  }, []);

  // Keep unread counts fresh on every page (paused while the tab is hidden).
  useEffect(() => {
    refresh();
    const timer = setInterval(() => !document.hidden && refresh(), LIST_POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const openChat = useCallback((requestId = null) => {
    setActiveId(requestId);
    setOpen(true);
  }, []);

  const totalUnread = chats.reduce((sum, c) => sum + c.unread, 0);

  return (
    <ChatContext.Provider
      value={{ open, setOpen, activeId, setActiveId, chats, refresh, openChat, totalUnread }}
    >
      {children}
    </ChatContext.Provider>
  );
}

export function useChat() {
  return useContext(ChatContext);
}
