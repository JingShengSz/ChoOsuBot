package cho.mrm;

import com.google.gson.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import me.replaymaster.Render;
import me.replaymaster.Encoder;
import me.replaymaster.beatmap.OsuMapReader;
import me.replaymaster.model.*;
import me.replaymaster.replay.IReplayReader;

/** Calls the upstream MRM drawing and encoding classes, without its interactive UI. */
public final class Bridge {
    private static int result(String name) {
        if (name.equals("perfect")) return 0;
        if (name.equals("great")) return 1;
        if (name.equals("good")) return 2;
        if (name.equals("miss")) return -1;
        throw new IllegalArgumentException("Unknown MRV judgement: " + name);
    }

    private static ReplayModel mrv(BeatMap map, JsonObject input) {
        JsonObject data = input.getAsJsonObject("resolved");
        Map<String, Note> byObject = new HashMap<>();
        for (Note note : map.getNotes()) {
            note.setDuration(0); // Verified MRV combination: Const + LN-to-note, 1x.
            byObject.put(note.getColumn() + ":" + note.getTimeStamp(), note);
        }
        List<Note> actions = new ArrayList<>();
        Map<Integer, List<Long>> releases = new HashMap<>();
        for (JsonElement entry : data.getAsJsonArray("releases")) {
            JsonObject row = entry.getAsJsonObject();
            releases.computeIfAbsent(row.get("key").getAsInt(), k -> new ArrayList<>())
                    .add(row.get("time").getAsLong());
        }
        for (JsonElement entry : data.getAsJsonArray("presses")) {
            JsonObject row = entry.getAsJsonObject();
            Note action = new Note();
            int key = row.get("key").getAsInt();
            long time = row.get("time").getAsLong();
            action.setColumn(key);
            action.setTimeStamp(time);
            long end = time;
            for (Long stamp : releases.getOrDefault(key, Collections.emptyList())) {
                if (stamp >= time) { end = stamp; break; }
            }
            action.setDuration(end - time);
            action.setShowAsLN(false);
            actions.add(action);
        }
        Set<Note> used = new HashSet<>();
        for (JsonElement entry : data.getAsJsonArray("recorded_judgements")) {
            JsonObject row = entry.getAsJsonObject();
            int key = row.get("key").getAsInt();
            long time = row.get("time").getAsLong();
            Note note = byObject.get(key + ":" + row.get("obj_time").getAsLong());
            if (note == null || !used.add(note)) throw new IllegalArgumentException("MRV object mismatch");
            int judge = result(row.get("result").getAsString());
            note.setJudgementStart(judge);
            note.setJudgementEnd(judge);
            // Link each successful judgement to its recorded press; extra presses stay red.
            if (judge >= 0) {
                Note best = null;
                long distance = 151;
                for (Note action : actions) {
                    long delta = Math.abs(action.getTimeStamp() - time);
                    if (action.getColumn() == key && action.getRelatedActionOrNote() == null && delta < distance) {
                        best = action; distance = delta;
                    }
                }
                if (best == null) throw new IllegalArgumentException("MRV judgement has no press");
                best.setJudgementStart(judge);
                best.setJudgementEnd(judge);
                best.setRelatedActionOrNote(note);
                note.setRelatedActionOrNote(best);
            }
        }
        if (used.size() != map.getNotes().size()) throw new IllegalArgumentException("Incomplete MRV judgements");
        Collections.sort(actions);
        return new ReplayModel(actions, 1.0, false, new double[]{52,92,126,150}, false);
    }

    public static void main(String[] args) throws Exception {
        JsonObject input = new JsonParser().parse(new String(Files.readAllBytes(new File(args[0]).toPath()),
                StandardCharsets.UTF_8)).getAsJsonObject();
        File work = new File(input.get("work").getAsString());
        Config config = new Config();
        config.setWidth(input.get("width").getAsInt());
        config.setHeight(input.get("height").getAsInt());
        config.setSpeed(input.get("scroll").getAsInt());
        config.setFramePerSecond(input.get("fps").getAsInt());
        config.setMalodyPE(input.get("platform").getAsString().equals("pe"));
        config.setServer(true);
        config.setDesktop(true);
        config.setOutputDir(work.getAbsolutePath());
        config.setFfmpegMaxProcessingSize(4);
        Config.Companion.setINSTANCE(config);
        BeatMap map = OsuMapReader.INSTANCE.readMap(input.get("map").getAsString());
        map.setBgmPath(input.get("audio").getAsString()); // Exact chosen difficulty's asset.
        if (!new File(map.getBgmPath()).isFile()) throw new FileNotFoundException("Missing chart audio");
        ReplayModel replay;
        if (input.get("format").getAsString().equals("mrv")) {
            replay = mrv(map, input);
        } else {
            File replayFile = new File(input.get("replay").getAsString());
            IReplayReader reader = IReplayReader.Companion.matchReplayReader(replayFile);
            if (reader == null) throw new IllegalArgumentException("Unsupported replay");
            replay = reader.readReplay(replayFile.getAbsolutePath(), map);
            long shift = Math.round(input.get("shift_ms").getAsDouble() / replay.getRate());
            if (replayFile.getName().endsWith(".mr")) {
                for (Note action : replay.getReplayData()) action.setTimeStamp(action.getTimeStamp() + shift);
            }
            reader.getJudger(map, replay).judge();
        }
        if (map.getNotes().isEmpty() || replay.getReplayData().isEmpty()) throw new IllegalArgumentException("Empty chart/replay");
        long end = 0;
        for (Note note : map.getNotes()) end = Math.max(end, note.getEndTime());
        for (Note action : replay.getReplayData()) end = Math.max(end, action.getEndTime());
        // Keep MRM's one-second lead-in, then trim it off in the delivery adapter.
        for (Note note : map.getNotes()) note.setTimeStamp(note.getTimeStamp() + 1000);
        for (Note action : replay.getReplayData()) action.setTimeStamp(action.getTimeStamp() + 1000);
        map.setDuration(end + 3000);
        int[] counts = new int[6]; // MAX/BEST, 300/COOL, 200/GOOD, 100, 50, MISS.
        for (Note note : map.getNotes()) counts[note.getJudgementStart() < 0 ? 5 : note.getJudgementStart()]++;
        JsonObject summary = new JsonObject();
        summary.addProperty("engine", "Mania-Replay-Master v2.4.0");
        summary.addProperty("duration", (end + 2000) / 1000.0);
        summary.addProperty("rate", replay.getRate());
        summary.add("counts", new Gson().toJsonTree(counts));
        Files.write(new File(work,"summary.json").toPath(), new Gson().toJson(summary).getBytes(StandardCharsets.UTF_8));
        File strips = new File(work,"strips.png");
        kotlin.Pair<Integer,Integer> shape = new Render(map, replay, strips).start();
        new Encoder(map, strips, new File(work,"mrm.mp4"), replay.getRate(), 1000,
                shape.getFirst(), input.get("ffmpeg").getAsString(), shape.getSecond()).generateVideo();
    }
}
