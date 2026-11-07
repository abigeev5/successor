import { useCallback, useEffect, useRef, useState } from "react";

export const MAX_SECONDS = 120;

type State = "idle" | "recording" | "unsupported";

export function useVoiceRecorder(onRecorded: (audio: Blob) => void) {
  const [state, setState] = useState<State>(
    typeof MediaRecorder === "undefined" || !navigator.mediaDevices ? "unsupported" : "idle",
  );
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);

  const stop = useCallback(() => {
    if (timer.current !== null) window.clearInterval(timer.current);
    timer.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
  }, []);

  const start = useCallback(async () => {
    setError(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("Нет доступа к микрофону. Разрешите его в настройках браузера.");
      return;
    }
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    const media = new MediaRecorder(stream, { mimeType });
    const chunks: Blob[] = [];
    media.ondataavailable = (event) => chunks.push(event.data);
    media.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      setState("idle");
      onRecorded(new Blob(chunks, { type: "audio/webm" }));
    };
    recorder.current = media;
    media.start();
    setSeconds(0);
    setState("recording");
    timer.current = window.setInterval(() => {
      setSeconds((s) => {
        if (s + 1 >= MAX_SECONDS) stop();
        return s + 1;
      });
    }, 1000);
  }, [onRecorded, stop]);

  useEffect(() => stop, [stop]);

  return { state, seconds, error, start, stop };
}
