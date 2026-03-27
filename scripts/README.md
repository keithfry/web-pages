# Scripts

## AI Techradar Agent — LaunchAgent

The agent runs daily at 8AM via a macOS LaunchAgent, which wakes the machine if asleep.

**Plist:** `scripts/com.keithfry.ai-techradar-agent.plist`
**Logs:** `logs/ai-techradar-agent.log`

### Install

```bash
cp scripts/com.keithfry.ai-techradar-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.keithfry.ai-techradar-agent.plist
```

### Run manually

```bash
launchctl start com.keithfry.ai-techradar-agent
```

### Disable

```bash
launchctl unload ~/Library/LaunchAgents/com.keithfry.ai-techradar-agent.plist
```

### Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.keithfry.ai-techradar-agent.plist
rm ~/Library/LaunchAgents/com.keithfry.ai-techradar-agent.plist
```

### Update after editing plist

```bash
launchctl unload ~/Library/LaunchAgents/com.keithfry.ai-techradar-agent.plist
cp scripts/com.keithfry.ai-techradar-agent.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.keithfry.ai-techradar-agent.plist
```
