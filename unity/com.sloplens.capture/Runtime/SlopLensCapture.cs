// SlopLens Capture — records what a player SEES and HEARS during an automated play session.
// Inert unless the player is launched with:  -sloplens-out <dir> [-sloplens-seconds 30]
// No hard dependencies: uGUI, TextMeshPro and the Input System are reached through reflection,
// so the package compiles in any project.
using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace SlopLens.Capture
{
    public static class Bootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void Init()
        {
            var args = Environment.GetCommandLineArgs();
            string outDir = Arg(args, "-sloplens-out");
            if (string.IsNullOrEmpty(outDir)) return;
            Directory.CreateDirectory(outDir);
            var go = new GameObject("~SlopLensCapture");
            UnityEngine.Object.DontDestroyOnLoad(go);
            var r = go.AddComponent<Runner>();
            r.outDir = outDir;
            float.TryParse(Arg(args, "-sloplens-seconds") ?? "30", out r.seconds);
        }

        internal static string Arg(string[] a, string k)
        {
            int i = Array.IndexOf(a, k);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }
    }

    /// Mutes the speakers while copying the final mix (so a capture run is silent on the user's machine).
    public class AudioTap : MonoBehaviour
    {
        public static readonly List<float> Mono = new List<float>(48000 * 30);
        public static int MaxSamples = 48000 * 30;
        public static bool Recording;
        void OnAudioFilterRead(float[] data, int channels)
        {
            if (Recording && Mono.Count < MaxSamples)
            {
                lock (Mono)
                {
                    for (int i = 0; i < data.Length; i += channels)
                    {
                        float s = 0; for (int c = 0; c < channels; c++) s += data[i + c];
                        Mono.Add(s / channels);
                    }
                }
            }
            Array.Clear(data, 0, data.Length);
        }
    }

    public class Runner : MonoBehaviour
    {
        public string outDir;
        public float seconds = 30f;

        readonly List<float> frameMs = new List<float>(4000);
        readonly List<string> shots = new List<string>();
        readonly List<Dictionary<string, object>> soundEvents = new List<Dictionary<string, object>>();
        readonly List<string> errors = new List<string>();
        readonly List<string> clicked = new List<string>();
        readonly Dictionary<AudioSource, float> lastTime = new Dictionary<AudioSource, float>();
        readonly Dictionary<string, Dictionary<string, object>> texts = new Dictionary<string, Dictionary<string, object>>();
        readonly HashSet<string> scenes = new HashSet<string>();
        float t0;
        System.Random rng = new System.Random(42);

        static readonly Regex StartLike = new Regex(@"^(▶\s*)?(play|start|start game|new game|continue|next|ok|confirm|tap to start|press any key|게임\s*시작|시작|플레이|계속|다음|확인|스테이지\s*1|1\s*스테이지|튜토리얼 건너뛰기|skip)\b", RegexOptions.IgnoreCase);
        static readonly Regex Risky = new Regex(@"(quit|exit|종료|나가기|delete|삭제|reset|초기화|settings|옵션|설정|credit|크레딧)", RegexOptions.IgnoreCase);

        void Awake()
        {
            Application.logMessageReceived += (msg, stack, type) =>
            {
                if ((type == LogType.Exception || type == LogType.Error) && errors.Count < 40) errors.Add(type + ": " + msg.Split('\n')[0]);
            };
            Application.runInBackground = true;
        }

        IEnumerator Start()
        {
            t0 = Time.realtimeSinceStartup;
            AudioTap.MaxSamples = AudioSettings.outputSampleRate * Mathf.Max(10, (int)seconds);
            StartCoroutine(PollLoop());
            float[] shotAt = { 1.5f, 0.2f * seconds, 0.35f * seconds, 0.5f * seconds, 0.65f * seconds, 0.8f * seconds, seconds - 1.5f };
            int si = 0;
            AudioTap.Recording = true;
            while (Time.realtimeSinceStartup - t0 < seconds)
            {
                float t = Time.realtimeSinceStartup - t0;
                if (si < shotAt.Length && t >= shotAt[si])
                {
                    string p = Path.Combine(outDir, $"frame-{si}-{Mathf.RoundToInt(t)}s.png");
                    ScreenCapture.CaptureScreenshot(p);
                    shots.Add(p);
                    si++;
                }
                yield return null;
            }
            AudioTap.Recording = false;
            yield return new WaitForSecondsRealtime(0.5f);
            WriteReport();
            Application.Quit();
        }

        void Update() { frameMs.Add(Time.unscaledDeltaTime * 1000f); }

        IEnumerator PollLoop()
        {
            float nextInput = 2f, nextUi = 1f, nextInventory = 0f;
            while (true)
            {
                float t = Time.realtimeSinceStartup - t0;
                EnsureTap();
                PollAudioSources(t);
                scenes.Add(SceneManager.GetActiveScene().name);
                if (t >= nextInventory) { InventoryTexts(); nextInventory = t + 2f; }
                if (t >= nextUi) { PressStartLikeButton(); nextUi = t + 2.5f; }
                if (t >= nextInput) { SimulateInput(); nextInput = t + 0.35f; }
                yield return new WaitForSecondsRealtime(0.1f);
            }
        }

        void EnsureTap()
        {
#if UNITY_2022_2_OR_NEWER
            var l = FindAnyObjectByType<AudioListener>();
#else
            var l = FindObjectOfType<AudioListener>();
#endif
            if (l != null && l.GetComponent<AudioTap>() == null) l.gameObject.AddComponent<AudioTap>();
        }

        static IEnumerable<T> All<T>() where T : UnityEngine.Object
        {
#if UNITY_2022_2_OR_NEWER
            return UnityEngine.Object.FindObjectsByType<T>(FindObjectsSortMode.None);
#else
            return UnityEngine.Object.FindObjectsOfType<T>();
#endif
        }

        void PollAudioSources(float t)
        {
            foreach (var s in All<AudioSource>())
            {
                if (s == null || s.clip == null) continue;
                float prev; bool seen = lastTime.TryGetValue(s, out prev);
                bool started = s.isPlaying && (s.time < prev || (prev == 0 && s.time < 0.3f) || !seen);
                if (started && soundEvents.Count < 600)
                    soundEvents.Add(new Dictionary<string, object> {
                        { "t", Math.Round(t, 2) }, { "clip", s.clip.name }, { "pitch", Math.Round(s.pitch, 3) }, { "volume", Math.Round(s.volume, 2) },
                        { "loop", s.loop }, { "length", Math.Round(s.clip.length, 2) }, { "source", s.gameObject.name } });
                lastTime[s] = s.isPlaying ? s.time : 0f;
            }
        }

        // ---------- on-screen text & fonts (uGUI Text and TextMeshPro via reflection)
        void InventoryTexts()
        {
            foreach (var mb in All<MonoBehaviour>())
            {
                if (mb == null || !mb.isActiveAndEnabled) continue;
                string tn = mb.GetType().FullName;
                if (tn != "TMPro.TextMeshProUGUI" && tn != "TMPro.TextMeshPro" && tn != "UnityEngine.UI.Text") continue;
                string txt = (mb.GetType().GetProperty("text")?.GetValue(mb) as string) ?? "";
                var fontObj = mb.GetType().GetProperty("font")?.GetValue(mb) as UnityEngine.Object;
                string key = tn + "|" + txt;
                if (string.IsNullOrWhiteSpace(txt) || texts.ContainsKey(key) || texts.Count > 400) continue;
                texts[key] = new Dictionary<string, object> {
                    { "text", txt.Length > 80 ? txt.Substring(0, 80) : txt }, { "font", fontObj != null ? fontObj.name : "" },
                    { "kind", tn.EndsWith("Text") && tn.StartsWith("UnityEngine") ? "uGUI" : "TMP" }, { "object", mb.gameObject.name } };
            }
        }

        // ---------- press start/next buttons so the session reaches gameplay
        void PressStartLikeButton()
        {
            foreach (var mb in All<MonoBehaviour>())
            {
                if (mb == null || !mb.isActiveAndEnabled || mb.GetType().FullName != "UnityEngine.UI.Button") continue;
                var interactable = mb.GetType().GetProperty("interactable")?.GetValue(mb);
                if (interactable is bool b && !b) continue;
                string label = LabelOf(mb.gameObject);
                if (string.IsNullOrEmpty(label) || Risky.IsMatch(label) || !StartLike.IsMatch(label.Trim())) continue;
                var onClick = mb.GetType().GetProperty("onClick")?.GetValue(mb);
                onClick?.GetType().GetMethod("Invoke", Type.EmptyTypes)?.Invoke(onClick, null);
                clicked.Add($"{Math.Round(Time.realtimeSinceStartup - t0, 1)}s: {label}");
                return;
            }
        }

        static string LabelOf(GameObject go)
        {
            foreach (var mb in go.GetComponentsInChildren<MonoBehaviour>(true))
            {
                string tn = mb.GetType().FullName;
                if (tn == "TMPro.TextMeshProUGUI" || tn == "TMPro.TextMeshPro" || tn == "UnityEngine.UI.Text")
                {
                    var s = mb.GetType().GetProperty("text")?.GetValue(mb) as string;
                    if (!string.IsNullOrWhiteSpace(s)) return s.Trim();
                }
            }
            return go.name;
        }

        // ---------- keyboard / mouse through the Input System (reflection; skipped when the package is absent)
        static Type T(string n) => Type.GetType(n + ", Unity.InputSystem");
        static readonly string[] Keys = { "Space", "LeftArrow", "RightArrow", "UpArrow", "DownArrow", "W", "A", "S", "D", "J", "K", "Z", "X", "Enter", "LeftShift", "E", "F" };
        bool inputWarned;
        void SimulateInput()
        {
            try
            {
                var kbT = T("UnityEngine.InputSystem.Keyboard"); var keyT = T("UnityEngine.InputSystem.Key");
                var stT = T("UnityEngine.InputSystem.LowLevel.KeyboardState"); var isT = T("UnityEngine.InputSystem.InputSystem");
                if (kbT == null || keyT == null || stT == null || isT == null) { if (!inputWarned) { errors.Add("info: Input System 없음 → 키 입력 시뮬레이션 생략 (레거시 Input은 외부에서 주입 불가)"); inputWarned = true; } return; }
                var kb = kbT.GetProperty("current")?.GetValue(null);
                if (kb == null) return;
                var queue = isT.GetMethods(BindingFlags.Public | BindingFlags.Static)
                    .First(m => m.Name == "QueueStateEvent" && m.IsGenericMethodDefinition && m.GetParameters().Length == 3).MakeGenericMethod(stT);
                var keys = Array.CreateInstance(keyT, rng.NextDouble() < 0.3 ? 2 : 1);
                for (int i = 0; i < keys.Length; i++) keys.SetValue(Enum.Parse(keyT, Keys[rng.Next(Keys.Length)]), i);
                var down = Activator.CreateInstance(stT, new object[] { keys });
                var up = Activator.CreateInstance(stT, new object[] { Array.CreateInstance(keyT, 0) });
                queue.Invoke(null, new object[] { kb, down, -1.0 });
                StartCoroutine(Release(queue, kb, up, 0.12f + (float)rng.NextDouble() * 0.2f));
                // mouse click at a random point around the screen centre
                var mT = T("UnityEngine.InputSystem.Mouse"); var msT = T("UnityEngine.InputSystem.LowLevel.MouseState");
                var mouse = mT?.GetProperty("current")?.GetValue(null);
                if (mouse != null && msT != null && rng.NextDouble() < 0.35)
                {
                    var mq = isT.GetMethods(BindingFlags.Public | BindingFlags.Static)
                        .First(m => m.Name == "QueueStateEvent" && m.IsGenericMethodDefinition && m.GetParameters().Length == 3).MakeGenericMethod(msT);
                    object st = Activator.CreateInstance(msT);
                    msT.GetField("position").SetValue(st, new Vector2(Screen.width * (0.3f + 0.4f * (float)rng.NextDouble()), Screen.height * (0.3f + 0.4f * (float)rng.NextDouble())));
                    msT.GetField("buttons").SetValue(st, (ushort)1);
                    mq.Invoke(null, new object[] { mouse, st, -1.0 });
                    object st2 = Activator.CreateInstance(msT); msT.GetField("position").SetValue(st2, msT.GetField("position").GetValue(st));
                    StartCoroutine(Release(mq, mouse, st2, 0.08f));
                }
            }
            catch (Exception e) { if (!inputWarned) { errors.Add("info: 입력 시뮬레이션 실패 " + e.GetType().Name); inputWarned = true; } }
        }

        IEnumerator Release(MethodInfo q, object dev, object state, float after)
        {
            yield return new WaitForSecondsRealtime(after);
            try { q.Invoke(null, new object[] { dev, state, -1.0 }); } catch { }
        }

        // ---------- output
        void WriteReport()
        {
            string wav = null;
            if (AudioTap.Mono.Count > AudioSettings.outputSampleRate / 2)
            {
                wav = Path.Combine(outDir, "mix.wav");
                WriteWav(wav, AudioTap.Mono, AudioSettings.outputSampleRate);
            }
            var sorted = frameMs.Skip(30).OrderBy(x => x).ToList();
            float median = sorted.Count > 0 ? sorted[sorted.Count / 2] : 0;
            float longShare = sorted.Count > 0 ? sorted.Count(x => x > 34f) / (float)sorted.Count : 0;
            bool fmod = Type.GetType("FMODUnity.RuntimeManager, FMODUnity") != null;
            var sb = new StringBuilder();
            sb.Append("{");
            sb.Append($"\"ok\":true,\"seconds\":{seconds},\"screen\":[{Screen.width},{Screen.height}],\"sampleRate\":{AudioSettings.outputSampleRate},");
            sb.Append($"\"medianFrameMs\":{median:0.00},\"longFrameShare\":{longShare:0.000},\"fmod\":{(fmod ? "true" : "false")},");
            sb.Append($"\"mixWav\":{Json(wav)},\"frames\":[{string.Join(",", shots.Select(Json))}],");
            sb.Append($"\"scenes\":[{string.Join(",", scenes.Select(Json))}],\"clicked\":[{string.Join(",", clicked.Select(Json))}],");
            sb.Append($"\"errors\":[{string.Join(",", errors.Select(Json))}],");
            sb.Append("\"soundEvents\":[" + string.Join(",", soundEvents.Select(Obj)) + "],");
            sb.Append("\"texts\":[" + string.Join(",", texts.Values.Select(Obj)) + "]");
            sb.Append("}");
            File.WriteAllText(Path.Combine(outDir, "capture.json"), sb.ToString(), new UTF8Encoding(false));
        }

        static string Json(string s) => s == null ? "null" : "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "") + "\"";
        static string Obj(Dictionary<string, object> d) => "{" + string.Join(",", d.Select(kv => Json(kv.Key) + ":" + Val(kv.Value))) + "}";
        static string Val(object v) => v is string s ? Json(s) : v is bool b ? (b ? "true" : "false") : Convert.ToString(v, System.Globalization.CultureInfo.InvariantCulture);

        static void WriteWav(string path, List<float> mono, int sr)
        {
            using (var w = new BinaryWriter(File.Create(path)))
            {
                int n = mono.Count;
                w.Write(Encoding.ASCII.GetBytes("RIFF")); w.Write(36 + n * 2); w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));
                w.Write(16); w.Write((short)1); w.Write((short)1); w.Write(sr); w.Write(sr * 2); w.Write((short)2); w.Write((short)16);
                w.Write(Encoding.ASCII.GetBytes("data")); w.Write(n * 2);
                foreach (var s in mono) w.Write((short)Mathf.Clamp(s * 32767f, -32768f, 32767f));
            }
        }
    }
}
