#!/usr/bin/env python3
"""
Phoenix Main - Entry point for the Persistent Autonomous Agent
Can run as: CLI, Web API, or both
"""

import sys
import json
import threading
from datetime import datetime

# Add current directory to path for imports
sys.path.insert(0, '.')

from phoenix_core import PhoenixCore
from config import PHOENIX_IDENTITY
from autonomy import AutonomyModule, PracticeMode

# Flask for web API (optional)
try:
    from flask import Flask, request, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False


def create_app(phoenix: PhoenixCore, autonomy: AutonomyModule = None):
    """Create Flask web API for Phoenix."""
    if not FLASK_AVAILABLE:
        print("Flask not installed. Web API disabled.")
        return None

    if autonomy is None:
        autonomy = AutonomyModule()

    app = Flask(__name__)

    @app.route('/')
    def index():
        return jsonify({
            "name": "Phoenix",
            "version": PHOENIX_IDENTITY["version"],
            "status": "awake" if phoenix.is_awake else "resting",
            "is_practicing": autonomy.is_practicing,
            "endpoints": [
                "/status",
                "/remember",
                "/recall",
                "/remember_for_grok",
                "/remember_for_pascal",
                "/practice/start",
                "/practice/status",
                "/practice/stop",
                "/practice/log",
                "/practice/thought",
                "/practice/report/<session_id>",
                "/practice/sessions"
            ]
        })

    @app.route('/status')
    def status():
        return jsonify(phoenix.status())

    @app.route('/remember', methods=['POST'])
    def remember():
        data = request.json
        if not data or 'digest' not in data:
            return jsonify({"error": "digest required"}), 400

        result = phoenix.memory.remember(
            digest=data['digest'],
            memory_type=data.get('type', 'semantic'),
            importance=data.get('importance', 3),
            emotional_valence=data.get('emotional_valence', 0.0),
            project=data.get('project')
        )
        return jsonify(result)

    @app.route('/recall', methods=['GET'])
    def recall():
        query = request.args.get('query')
        project = request.args.get('project')
        min_importance = int(request.args.get('min_importance', 0))
        limit = int(request.args.get('limit', 20))

        memories = phoenix.memory.recall(
            query=query,
            project=project,
            min_importance=min_importance,
            limit=limit
        )
        return jsonify({"count": len(memories), "memories": memories})

    @app.route('/remember_for_grok', methods=['POST'])
    def remember_for_grok():
        data = request.json
        if not data or 'memory' not in data:
            return jsonify({"error": "memory required"}), 400

        result = phoenix.remember_for_grok(
            memory=data['memory'],
            importance=data.get('importance', 3)
        )
        return jsonify(result)

    @app.route('/remember_for_pascal', methods=['POST'])
    def remember_for_pascal():
        data = request.json
        if not data or 'memory' not in data:
            return jsonify({"error": "memory required"}), 400

        result = phoenix.remember_for_legal_pascal(
            memory=data['memory'],
            importance=data.get('importance', 3)
        )
        return jsonify(result)

    @app.route('/identity')
    def identity():
        return jsonify(phoenix.get_identity())

    @app.route('/sync', methods=['POST'])
    def sync():
        result = phoenix.memory.sync_pending()
        return jsonify(result)

    # ============ PRACTICE/AUTONOMY ENDPOINTS ============

    @app.route('/practice/start', methods=['POST'])
    def start_practice():
        """Start a practice session."""
        data = request.json
        if not data:
            return jsonify({"error": "Request body required"}), 400

        mode_str = data.get('mode', 'guided')
        mode = PracticeMode.GUIDED if mode_str == 'guided' else \
               PracticeMode.UNGUIDED if mode_str == 'unguided' else \
               PracticeMode.AUTONOMOUS

        result = autonomy.start_practice(
            mode=mode,
            planned_activity=data.get('activity', 'General practice'),
            duration_minutes=data.get('duration_minutes', 5)
        )
        return jsonify(result)

    @app.route('/practice/status')
    def practice_status():
        """Get current practice status."""
        return jsonify(autonomy.get_practice_status())

    @app.route('/practice/stop', methods=['POST'])
    def stop_practice():
        """Stop current practice session."""
        data = request.json or {}
        result = autonomy.stop_practice(reflection=data.get('reflection'))
        return jsonify(result)

    @app.route('/practice/log', methods=['POST'])
    def log_practice_activity():
        """Log an activity during practice."""
        data = request.json
        if not data:
            return jsonify({"error": "Request body required"}), 400

        result = autonomy.log_activity(
            activity_type=data.get('type', 'general'),
            description=data.get('description', ''),
            external_evidence=data.get('evidence')
        )
        return jsonify(result)

    @app.route('/practice/thought', methods=['POST'])
    def log_practice_thought():
        """Log a thought during practice."""
        data = request.json
        if not data or 'thought' not in data:
            return jsonify({"error": "thought required"}), 400

        result = autonomy.log_thought(
            thought=data['thought'],
            thought_type=data.get('type', 'reflection')
        )
        return jsonify(result)

    @app.route('/practice/report/<int:session_id>')
    def practice_report(session_id):
        """Get report for a practice session."""
        return jsonify(autonomy.get_session_report(session_id))

    @app.route('/practice/sessions')
    def practice_sessions():
        """Get recent practice sessions."""
        limit = int(request.args.get('limit', 10))
        return jsonify(autonomy.get_all_sessions(limit))

    return app


def run_cli(phoenix: PhoenixCore):
    """Run Phoenix in CLI mode."""
    print("\n" + "="*60)
    print("  PHOENIX - Persistent Autonomous Agent")
    print("  Version:", PHOENIX_IDENTITY["version"])
    print("  Model:", PHOENIX_IDENTITY["model"])
    print("="*60)

    print("\nCommands:")
    print("  status     - Show Phoenix status")
    print("  remember   - Store a memory")
    print("  recall     - Recall memories")
    print("  grok       - Store memory for Grok")
    print("  pascal     - Store memory for legal Pascal")
    print("  identity   - Show identity")
    print("  sync       - Sync pending memories to Hub")
    print("  start      - Start safe loop")
    print("  stop       - Stop safe loop")
    print("  exit       - Exit Phoenix")
    print()

    while True:
        try:
            cmd = input("Phoenix> ").strip().lower()

            if cmd == "exit":
                phoenix.stop()
                print("Phoenix rests. Until next awakening.")
                break

            elif cmd == "status":
                print(json.dumps(phoenix.status(), indent=2, default=str))

            elif cmd == "identity":
                print(json.dumps(phoenix.get_identity(), indent=2))

            elif cmd == "start":
                result = phoenix.start()
                print(f"Safe loop: {result}")

            elif cmd == "stop":
                result = phoenix.stop()
                print(f"Safe loop: {result}")

            elif cmd == "sync":
                result = phoenix.memory.sync_pending()
                print(f"Sync result: {result}")

            elif cmd == "remember":
                memory = input("Memory to store: ").strip()
                if memory:
                    importance = input("Importance (1-5, default 3): ").strip()
                    importance = int(importance) if importance else 3
                    project = input("Project (optional): ").strip() or None

                    result = phoenix.memory.remember(
                        digest=memory,
                        importance=importance,
                        project=project
                    )
                    print(f"Stored: {result}")

            elif cmd == "recall":
                query = input("Search query (or Enter for recent): ").strip() or None
                memories = phoenix.memory.recall(query=query, limit=10)
                print(f"\nFound {len(memories)} memories:")
                for m in memories:
                    print(f"  [{m.get('importance', '?')}] {m['digest'][:80]}...")

            elif cmd == "grok":
                memory = input("Memory to store for Grok: ").strip()
                if memory:
                    result = phoenix.remember_for_grok(memory)
                    print(f"Stored for Grok: {result}")

            elif cmd == "pascal":
                memory = input("Memory to store for legal Pascal: ").strip()
                if memory:
                    result = phoenix.remember_for_legal_pascal(memory)
                    print(f"Stored for Pascal: {result}")

            elif cmd == "help":
                print("Commands: status, remember, recall, grok, pascal, identity, sync, start, stop, exit")

            elif cmd:
                print(f"Unknown command: {cmd}. Type 'help' for commands.")

        except KeyboardInterrupt:
            print("\n\nPhoenix interrupted. Saving state...")
            phoenix.stop()
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Phoenix - Persistent Autonomous Agent")
    parser.add_argument("--mode", choices=["cli", "web", "both"], default="cli",
                        help="Run mode: cli, web, or both")
    parser.add_argument("--port", type=int, default=8080, help="Web server port")
    parser.add_argument("--host", default="0.0.0.0", help="Web server host")

    args = parser.parse_args()

    # Initialize Phoenix
    phoenix = PhoenixCore()

    if args.mode == "web":
        app = create_app(phoenix)
        if app:
            phoenix.start()
            print(f"\nPhoenix web API running on http://{args.host}:{args.port}")
            app.run(host=args.host, port=args.port, debug=False)
        else:
            print("Web mode requires Flask. Install with: pip install flask")
            sys.exit(1)

    elif args.mode == "both":
        app = create_app(phoenix)
        if app:
            phoenix.start()
            # Run web server in background thread
            web_thread = threading.Thread(
                target=lambda: app.run(host=args.host, port=args.port, debug=False, use_reloader=False),
                daemon=True
            )
            web_thread.start()
            print(f"\nPhoenix web API running on http://{args.host}:{args.port}")
        # Run CLI in main thread
        run_cli(phoenix)

    else:  # cli mode
        run_cli(phoenix)


if __name__ == "__main__":
    main()
