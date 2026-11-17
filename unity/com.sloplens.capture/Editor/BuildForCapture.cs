// Unity CLI entry point:
//   Unity.exe -batchmode -quit -projectPath <copy> -executeMethod SlopLens.Capture.Editor.BuildForCapture.Run -sloplensBuild <dir>
using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace SlopLens.Capture.Editor
{
    public static class BuildForCapture
    {
        public static void Run()
        {
            var args = Environment.GetCommandLineArgs();
            int i = Array.IndexOf(args, "-sloplensBuild");
            string dir = i >= 0 && i + 1 < args.Length ? args[i + 1] : Path.Combine(Directory.GetCurrentDirectory(), "SlopLensBuild");
            Directory.CreateDirectory(dir);

            // Build Settings may reference scenes that were moved or deleted: keep only existing ones
            var scenes = EditorBuildSettings.scenes.Where(s => s.enabled && File.Exists(s.path)).Select(s => s.path).ToArray();
            if (scenes.Length == 0)
            {
                var all = AssetDatabase.FindAssets("t:Scene", new[] { "Assets" }).Select(AssetDatabase.GUIDToAssetPath)
                    .Where(p => !System.Text.RegularExpressions.Regex.IsMatch(p, "TutorialInfo|TextMesh Pro|_Recovery|Test|Demo|Sample|Anim|Sandbox|Plugins",
                        System.Text.RegularExpressions.RegexOptions.IgnoreCase)).ToList();
                System.Func<string, int> rank = p => {
                    var n = System.IO.Path.GetFileNameWithoutExtension(p);
                    if (System.Text.RegularExpressions.Regex.IsMatch(n, "title|main|menu|lobby|start|intro|boot|타이틀|메인|로비", System.Text.RegularExpressions.RegexOptions.IgnoreCase)) return 0;
                    if (System.Text.RegularExpressions.Regex.IsMatch(n, "game|play|stage|level|world|인게임|스테이지", System.Text.RegularExpressions.RegexOptions.IgnoreCase)) return 1;
                    return 2; };
                var start = all.OrderBy(rank).ThenBy(p => p.Length).ToList();
                scenes = start.Take(1).ToArray();
            }

            var opts = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = Path.Combine(dir, "Game.exe"),
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None,
            };
            var report = BuildPipeline.BuildPlayer(opts);
            var s = report.summary;
            File.WriteAllText(Path.Combine(dir, "build.json"),
                "{\"result\":\"" + s.result + "\",\"errors\":" + s.totalErrors + ",\"seconds\":" + (int)s.totalTime.TotalSeconds +
                ",\"scenes\":[" + string.Join(",", scenes.Select(x => "\"" + x.Replace("\\", "/") + "\"")) + "]}");
            EditorApplication.Exit(s.result == BuildResult.Succeeded ? 0 : 1);
        }
    }
}
