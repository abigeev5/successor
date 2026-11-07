import { useCallback, useEffect, useRef, useState } from "react";

export const MAX_MINUTES = 30;

type State = "idle" | "recording" | "unsupported";

function pickMime(): string {
  const options = [
    "video/webm;codecs=vp9,opus",
    "video/webm;codecs=vp8,opus",
    "video/webm",
    "video/mp4",
  ];
  return options.find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
}

/**
 * Screen and microphone go into one MediaRecorder. Recording stops at MAX_MINUTES or when the user
 * ends sharing in the browser.
 */
export function useScreenRecorder(onRecorded: (video: Blob) => void) {
  const [state, setState] = useState<State>(
    typeof MediaRecorder === "undefined" || !navigator.mediaDevices?.getDisplayMedia
      ? "unsupported"
      : "idle",
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
    let screen: MediaStream;
    try {
      screen = await navigator.mediaDevices.getDisplayMedia({ video: true });
    } catch {
      setError("Запись не началась: доступ к экрану не дали.");
      return;
    }
    let voice: MediaStream;
    try {
      voice = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      screen.getTracks().forEach((t) => t.stop());
      setError("Нужен микрофон: шаги инструкции выделяются по вашему комментарию.");
      return;
    }
    const stream = new MediaStream([...screen.getVideoTracks(), ...voice.getAudioTracks()]);
    const mimeType = pickMime();
    const media = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 1_500_000 });
    const chunks: Blob[] = [];
    media.ondataavailable = (event) => event.data.size && chunks.push(event.data);
    media.onstop = () => {
      [...screen.getTracks(), ...voice.getTracks()].forEach((t) => t.stop());
      setState("idle");
      onRecorded(new Blob(chunks, { type: mimeType.split(";")[0] || "video/webm" }));
    };
    screen.getVideoTracks()[0].onended = stop; // «Прекратить доступ» in the browser bar
    recorder.current = media;
    media.start(1000);
    setSeconds(0);
    setState("recording");
    timer.current = window.setInterval(() => {
      setSeconds((s) => {
        if (s + 1 >= MAX_MINUTES * 60) stop();
        return s + 1;
      });
    }, 1000);
  }, [onRecorded, stop]);

  useEffect(() => stop, [stop]);

  return { state, seconds, error, start, stop };
}
