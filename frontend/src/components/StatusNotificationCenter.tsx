import { useEffect, useRef, useState, type ReactNode } from "react";

import { AlertIcon, CheckIcon, InfoIcon, XIcon } from "./icons";

export type StatusNotificationTone = "error" | "info" | "success" | "warning";

type StatusNotificationAction = {
  label: string;
  onClick: () => void;
};

type StatusNotificationInput = {
  action?: StatusNotificationAction;
  durationMs?: number | null;
  id?: string;
  message: string;
  title?: string;
  tone?: StatusNotificationTone;
};

type StatusNotification = StatusNotificationInput & {
  id: string;
  tone: StatusNotificationTone;
};

type StatusNotificationListener = (notification: StatusNotification) => void;

const listeners = new Set<StatusNotificationListener>();
const dismissListeners = new Set<(notificationId: string) => void>();
const pendingNotifications: StatusNotification[] = [];
let notificationSequence = 0;

const TONE_LABEL: Record<StatusNotificationTone, string> = {
  error: "错误",
  info: "提示",
  success: "成功",
  warning: "注意"
};

const TONE_MARK: Record<StatusNotificationTone, ReactNode> = {
  error: <XIcon />,
  info: <InfoIcon />,
  success: <CheckIcon />,
  warning: <AlertIcon />
};

function notificationDuration(notification: StatusNotification) {
  if (notification.durationMs !== undefined) {
    return notification.durationMs;
  }
  if (notification.tone === "error") {
    return null;
  }
  return notification.tone === "success" ? 3600 : 5200;
}

export function showStatusNotification(input: StatusNotificationInput) {
  const message = input.message.trim();
  if (!message) {
    return;
  }
  const notification: StatusNotification = {
    ...input,
    id: input.id ?? `status-notification-${Date.now()}-${notificationSequence++}`,
    message,
    tone: input.tone ?? "info"
  };
  if (!listeners.size) {
    pendingNotifications.push(notification);
    return;
  }
  listeners.forEach((listener) => listener(notification));
}

function dismissStatusNotification(notificationId: string) {
  for (let index = pendingNotifications.length - 1; index >= 0; index -= 1) {
    if (pendingNotifications[index].id === notificationId) {
      pendingNotifications.splice(index, 1);
    }
  }
  dismissListeners.forEach((listener) => listener(notificationId));
}

export function useStatusNotification(
  message: string | null | undefined,
  options: Omit<StatusNotificationInput, "message"> = {}
) {
  const actionRef = useRef(options.action);
  const lastMessageRef = useRef("");
  actionRef.current = options.action;

  useEffect(() => {
    const nextMessage = message?.trim() ?? "";
    if (!nextMessage) {
      if (lastMessageRef.current && options.id) {
        dismissStatusNotification(options.id);
      }
      lastMessageRef.current = "";
      return;
    }
    const fingerprint = [options.id, options.tone, options.title, nextMessage].join("|");
    if (lastMessageRef.current === fingerprint) {
      return;
    }
    lastMessageRef.current = fingerprint;
    showStatusNotification({
      ...options,
      action: actionRef.current,
      message: nextMessage
    });
  }, [message, options.durationMs, options.id, options.title, options.tone]);
}

export function StatusNotificationCenter() {
  const [notifications, setNotifications] = useState<StatusNotification[]>([]);
  const timersRef = useRef(new Map<string, number>());

  function dismiss(notificationId: string) {
    const timer = timersRef.current.get(notificationId);
    if (timer !== undefined) {
      window.clearTimeout(timer);
      timersRef.current.delete(notificationId);
    }
    setNotifications((current) => current.filter((item) => item.id !== notificationId));
  }

  useEffect(() => {
    const timers = timersRef.current;
    const receive: StatusNotificationListener = (notification) => {
      setNotifications((current) => {
        const withoutSameId = current.filter((item) => item.id !== notification.id);
        return [notification, ...withoutSameId].slice(0, 4);
      });
      const previousTimer = timers.get(notification.id);
      if (previousTimer !== undefined) {
        window.clearTimeout(previousTimer);
      }
      const duration = notificationDuration(notification);
      if (duration !== null) {
        timers.set(
          notification.id,
          window.setTimeout(() => dismiss(notification.id), duration)
        );
      }
    };

    listeners.add(receive);
    dismissListeners.add(dismiss);
    pendingNotifications.splice(0).forEach(receive);
    return () => {
      listeners.delete(receive);
      dismissListeners.delete(dismiss);
      timers.forEach((timer) => window.clearTimeout(timer));
      timers.clear();
    };
  }, []);

  if (!notifications.length) {
    return null;
  }

  return (
    <aside aria-label="状态通知" className="status-notification-region">
      {notifications.map((notification) => (
        <section
          className="status-notification"
          data-tone={notification.tone}
          key={notification.id}
          role={notification.tone === "error" ? "alert" : "status"}
        >
          <span aria-hidden="true" className="status-notification-mark">
            {TONE_MARK[notification.tone]}
          </span>
          <div className="status-notification-copy">
            <span className="status-notification-kicker">{TONE_LABEL[notification.tone]}</span>
            {notification.title ? <strong>{notification.title}</strong> : null}
            <p>{notification.message}</p>
            {notification.action ? (
              <button
                className="status-notification-action"
                onClick={() => {
                  notification.action?.onClick();
                  dismiss(notification.id);
                }}
                type="button"
              >
                {notification.action.label}
              </button>
            ) : null}
          </div>
          <button
            aria-label="关闭通知"
            className="status-notification-close"
            onClick={() => dismiss(notification.id)}
            type="button"
          >
            <XIcon />
          </button>
        </section>
      ))}
    </aside>
  );
}
