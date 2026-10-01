# ecobee Thermostat Integration for Unfolded Circle Remote 2/3

Control your **ecobee smart thermostats** directly from your Unfolded Circle Remote 2 or Remote 3. HVAC mode, target temperature and range, fan, comfort settings (Home / Away / Sleep), humidifier, Aux Heat, ventilator, plus sensors for every room sensor, occupancy, weather and air quality - for every thermostat on your ecobee account.

![ecobee](https://img.shields.io/badge/ecobee-Smart%20Thermostats-3B9C3B)
[![GitHub Release](https://img.shields.io/github/v/release/mase1981/uc-intg-ecobee?style=flat-square)](https://github.com/mase1981/uc-intg-ecobee/releases)
![License](https://img.shields.io/badge/license-MPL--2.0-blue?style=flat-square)
[![GitHub issues](https://img.shields.io/github/issues/mase1981/uc-intg-ecobee?style=flat-square)](https://github.com/mase1981/uc-intg-ecobee/issues)
[![Community Forum](https://img.shields.io/badge/community-forum-blue?style=flat-square)](https://unfolded.community/)
[![Discord](https://badgen.net/discord/online-members/zGVYf58)](https://discord.gg/zGVYf58)
![GitHub Downloads (all assets, all releases)](https://img.shields.io/github/downloads/mase1981/uc-intg-ecobee/total?style=flat-square)
[![Buy Me A Coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=flat-square)](https://buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-donate-blue.svg?style=flat-square)](https://paypal.me/mmiyara)
[![Github Sponsors](https://img.shields.io/badge/GitHub%20Sponsors-30363D?&logo=GitHub-Sponsors&logoColor=EA4AAA&style=flat-square)](https://github.com/sponsors/mase1981)

## Supported Devices

All thermostats on your ecobee account that the ecobee cloud API supports, including **ecobee Smart Thermostat Premium**, **Smart Thermostat Enhanced**, **Smart Thermostat with Voice Control**, **ecobee3 / ecobee3 lite**, **ecobee4**, **Si / Smart / EMS** models and **Carrier/Bryant Cor**. ecobee room sensors (temperature + occupancy) are added automatically.

## Features

- **🌡️ Climate entity per thermostat** - Off / Heat / Cool / Heat-Cool (auto), target temperature, target range in auto mode, fan Auto/On. Uses the thermostat's own °F/°C setting and setpoint limits.
- **🎛️ Remote entity per thermostat** - simple commands for Activities: power, Temp +/-, modes, Home / Away / Sleep, Away Indefinitely, Resume Schedule, Fan Auto/On, with physical button mapping (volume/channel/D-pad up-down = temperature) and a button page.
- **🏠 Comfort setting selector** - your ecobee comfort settings (Home, Away, Sleep and custom ones), Away Indefinitely and Resume Schedule. Holds follow the thermostat's own "hold action" preference.
- **🌀 Fan** - Fan Mode (Auto / On) and Fan Min On Time selectors.
- **💧 Humidifier** - Humidifier Mode and Target Humidity selectors (when a humidifier is installed).
- **🔥 Switches** - Aux Heat Only (heat pumps) and Ventilator 20-minute timer (when a ventilator is installed).
- **📊 Sensors** - temperature, humidity, current activity (Heating / Cooling / Fan / Idle), HVAC mode, comfort setting, outdoor temperature & humidity, weather, model, every room sensor's temperature and occupancy, and CO2 / VOC / air quality score (Smart Premium).
- **🔐 Sign in with your ecobee account** - email + password with two-step verification (MFA) support, or a legacy developer API key + PIN.

---
## ❤️ Support Development ❤️

If you find this integration useful, consider supporting development:

[![GitHub Sponsors](https://img.shields.io/badge/Sponsor-GitHub-pink?style=for-the-badge&logo=github)](https://github.com/sponsors/mase1981)
[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://www.buymeacoffee.com/meirmiyara)
[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/mmiyara)

Your support helps maintain this integration. Thank you! ❤️
---

## How It Works

ecobee thermostats are controlled through the **ecobee cloud API** (there is no local API), using the same [python-ecobee-api](https://github.com/nkgilley/python-ecobee-api) library as the Home Assistant ecobee integration.

- **Polling every 3 minutes** - ecobee asks API clients not to poll more often. After every command the integration refreshes immediately, so changes made from the Remote show up right away.
- **Tokens are kept, not your session** - after sign-in, a refresh token is stored and renewed automatically. If ecobee ever rejects it, the integration signs in again with the stored credentials; if that needs a new verification code, the thermostats show as unavailable and you re-run setup.
- **Holds** - temperature and comfort-setting changes are holds that follow the thermostat's "hold action" preference (until next schedule change, 2 h, 4 h or indefinite). Use **Resume Schedule** to cancel a hold.

> **Developer API keys:** ecobee no longer issues new developer API keys. Use your normal ecobee account email and password; the API key option is only for people who already have a key.

## Requirements

- An ecobee account with at least one thermostat.
- Internet access for the Remote (ecobee is cloud-only).
- Unfolded Circle Remote 2 / 3 with firmware supporting custom integrations.

## Installation

### Option 1: Remote Web Interface (Recommended)

1. Download the latest `uc-intg-ecobee-<version>-aarch64.tar.gz` from the [**Releases**](https://github.com/mase1981/uc-intg-ecobee/releases) page.
2. Open your Remote's web interface (`http://your-remote-ip`).
3. Go to **Settings -> Integrations -> Add Integration -> Install Custom** and upload the `.tar.gz`.

### Option 2: Docker (Advanced Users)

**Image**: `ghcr.io/mase1981/uc-intg-ecobee:latest`

**Docker Compose:**
```yaml
services:
  uc-intg-ecobee:
    image: ghcr.io/mase1981/uc-intg-ecobee:latest
    container_name: uc-intg-ecobee
    network_mode: host
    volumes:
      - ./config:/config
    environment:
      - UC_CONFIG_HOME=/config
      - UC_INTEGRATION_HTTP_PORT=9090
      - UC_INTEGRATION_INTERFACE=0.0.0.0
      - PYTHONPATH=/app
    restart: unless-stopped
```

**Docker Run:**
```bash
docker run -d --name uc-intg-ecobee --restart unless-stopped --network host -v $(pwd)/config:/config -e UC_CONFIG_HOME=/config -e UC_INTEGRATION_INTERFACE=0.0.0.0 -e UC_INTEGRATION_HTTP_PORT=9090 -e PYTHONPATH=/app ghcr.io/mase1981/uc-intg-ecobee:latest
```

## Configuration

1. Start setup and enter your **ecobee email and password** (leave the API key empty).
2. If your account uses two-step verification, enter the **verification code** on the next screen.
3. All thermostats on the account are added.

**Legacy developer API key:** leave email and password empty and enter the API key. The next screen shows a **PIN** - go to [ecobee.com](https://www.ecobee.com/consumerportal/index.html), open **My Apps -> Add Application**, enter the PIN, click **Authorize**, then continue setup.

For each thermostat the integration creates:

| Entity | Purpose |
|--------|---------|
| **Climate** (`<thermostat>`) | Mode, target temperature / range, fan. |
| **Remote** (`<thermostat> Remote`) | Simple commands and button mapping for Activities. |
| **Selects** | Comfort Setting, Fan Mode, Fan Min On Time, Humidifier Mode*, Target Humidity*. |
| **Switches** | Aux Heat Only*, Ventilator 20m Timer*. |
| **Sensors** | Temperature, Humidity, Activity, HVAC Mode, Comfort Setting, Outdoor Temperature/Humidity, Weather, Model, Occupancy, room sensor Temperature/Occupancy, CO2/VOC/Air Quality*. |

\* only when the equipment / sensor is present.

### Remote simple commands

`POWER_TOGGLE`, `POWER_ON`, `POWER_OFF`, `TEMP_UP`, `TEMP_DOWN`, `MODE_HEAT`, `MODE_COOL`, `MODE_AUTO`, `MODE_OFF`, `PRESET_HOME`, `PRESET_AWAY`, `PRESET_SLEEP`, `PRESET_AWAY_INDEFINITELY`, `RESUME_SCHEDULE`, `FAN_AUTO`, `FAN_ON`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Setup fails with an authorization error | Check the email/password (or verification code). Do not fill in both the API key and the email/password. |
| Thermostats become unavailable and the log says "Re-run the integration setup" | ecobee rejected the stored sign-in (e.g. password changed or a new verification code is needed). Run setup again. |
| A thermostat is unavailable but others work | The thermostat is offline in the ecobee cloud (check the ecobee app). |
| Changes made in the ecobee app take a while to appear | The integration polls every 3 minutes (ecobee's recommended minimum). |
| A new thermostat or room sensor is missing | Restart the integration (or re-run setup) after adding equipment to your ecobee account. |

## Credits

- **Developer**: Meir Miyara
- **ecobee API**: based on [python-ecobee-api](https://github.com/nkgilley/python-ecobee-api) and the Home Assistant [ecobee integration](https://www.home-assistant.io/integrations/ecobee/).
- **Unfolded Circle**: Remote 2/3 integration framework ([ucapi](https://github.com/unfoldedcircle/integration-python-library) / [ucapi-framework](https://github.com/JackJPowell/ucapi-framework)).

## License

Mozilla Public License 2.0 (MPL-2.0) - see the LICENSE file.

## Support & Community

- **GitHub Issues**: [Report bugs and request features](https://github.com/mase1981/uc-intg-ecobee/issues)
- **UC Community Forum**: [General discussion and support](https://unfolded.community/)
- **Developer**: [Meir Miyara](https://www.linkedin.com/in/meirmiyara)

---

**Made with ❤️ for the Unfolded Circle Community**

**Thank You**: Meir Miyara
