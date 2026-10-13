import { useEffect, useState } from "react";
import { getHistoricalVessels, getVesselTrack, VesselApiError } from "@/services/vessels";
import type { ApiTrackPoint, ApiVessel } from "@/types/vessels";

interface HistoricalTrackBrowserProps {
  selectedVesselId: string | null;
  points: ApiTrackPoint[];
  isPlaying: boolean;
  playbackIndex: number;
  onTrackLoaded: (vessel: ApiVessel, points: ApiTrackPoint[]) => void;
  onPlaybackToggle: () => void;
  onPlaybackIndexChange: (index: number) => void;
}

export function HistoricalTrackBrowser({
  selectedVesselId,
  points,
  isPlaying,
  playbackIndex,
  onTrackLoaded,
  onPlaybackToggle,
  onPlaybackIndexChange,
}: HistoricalTrackBrowserProps) {
  const [vessels, setVessels] = useState<ApiVessel[]>([]);
  const [vesselId, setVesselId] = useState(selectedVesselId ?? "");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("正在加载已记录船舶…");

  useEffect(() => {
    let cancelled = false;
    getHistoricalVessels()
      .then(result => {
        if (cancelled) return;
        setVessels(result);
        setVesselId(current => current || result[0]?.id || "");
        setMessage(result.length ? "选择船舶后加载历史轨迹" : "暂无已记录船舶");
      })
      .catch(() => {
        if (!cancelled) setMessage("无法加载已记录船舶。");
      });
    return () => { cancelled = true; };
  }, []);

  const loadTrack = async () => {
    const vessel = vessels.find(candidate => candidate.id === vesselId);
    if (!vessel || loading) return;
    setLoading(true);
    setMessage("正在读取历史轨迹…");
    try {
      const track = await getVesselTrack(vessel.id);
      onTrackLoaded(vessel, track);
      setMessage(track.length ? `${track.length} 个历史位置点` : "该船暂无历史位置记录");
    } catch (error) {
      setMessage(error instanceof VesselApiError ? error.message : "无法读取历史轨迹。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="voyage-history-browser historical-track-browser">
      <span className="voyage-history-heading">历史航迹</span>
      <label className="voyage-history-search">
        <span className="sr-only">选择船舶</span>
        <select value={vesselId} onChange={event => setVesselId(event.target.value)} disabled={!vessels.length}>
          {!vessels.length && <option value="">暂无船舶</option>}
          {vessels.map(vessel => <option key={vessel.id} value={vessel.id}>{vessel.name || vessel.mmsi || vessel.id}</option>)}
        </select>
      </label>
      <button type="button" className="historical-track-load" onClick={loadTrack} disabled={!vesselId || loading}>
        {loading ? "读取中…" : "加载历史轨迹"}
      </button>
      <small className="voyage-history-empty">{message}</small>
      {points.length > 1 && (
        <div className="historical-track-playback">
          <input
            type="range"
            min={0}
            max={points.length - 1}
            value={playbackIndex}
            onChange={event => onPlaybackIndexChange(Number(event.target.value))}
            aria-label="历史轨迹播放进度"
          />
          <button type="button" onClick={onPlaybackToggle}>{isPlaying ? "暂停" : "播放"}</button>
          <small>{playbackIndex + 1} / {points.length}</small>
        </div>
      )}
    </div>
  );
}