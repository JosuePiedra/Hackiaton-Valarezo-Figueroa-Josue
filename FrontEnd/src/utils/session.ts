import { v4 as uuidv4 } from 'uuid';

const SESSION_KEY = 'copagocare_session_id';

export const getOrCreateSessionId = (): string => {
  let sessionId = localStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId = uuidv4();
    localStorage.setItem(SESSION_KEY, sessionId);
  }
  return sessionId;
};

export const resetSessionId = (): string => {
  const newSessionId = uuidv4();
  localStorage.setItem(SESSION_KEY, newSessionId);
  return newSessionId;
};
