# gr-selector 📡

## Description 📝

The **multiselector_ntp_samples_scheduled** block is a custom GNU Radio block that cyclically selects a complex input signal to multiple output ports, synchronizing transmission start with an NTP time reference.

This block alternates between active transmitter outputs and a silence period output according to a precise schedule based on sample counts at a configured sample rate. Using NTP synchronization allows precise timing alignment across multiple devices.

## Key Features ✨

- ⏰ NTP synchronization for precise transmission start timing
- 📊 Configurable number of active transmitters (outputs)
- 🔇 Automatic silence periods between transmitter switches
- 📅 Precomputed scheduling based on sample counts for deterministic timing
- 🌐 Support for custom NTP servers and sync intervals

## Parameters ⚙️

- `num_outputs`: Number of active transmitters (total outputs = num_outputs + 1)
- `switch_period_ms`: Duration each transmitter is active (milliseconds)
- `switch_delay_ms`: Duration of silence between transmitter switches (milliseconds)
- `ntp_start_time_str`: Start time in HH:MM:SS format (empty starts at next minute)
- `samp_rate`: Sample rate in Hz
- `ntp_servers`: Comma-separated list of NTP servers (default servers are used if empty)
- `sync_interval`: NTP resynchronization interval in seconds

## Output Mapping 🗺️

- Outputs `tx_0` to `tx_(num_outputs-1)`: Active transmitters
- Output `silence`: Transmits during silence periods

## Timing Example ⏱️

With 3 transmitters, `switch_period_ms=1000` ms and `switch_delay_ms=200` ms starting at 14:30:00:

- 14:30:00.000 → Transmitter 0 active for 1000 ms
- 14:30:01.000 → Silence for 200 ms
- 14:30:01.200 → Transmitter 1 active for 1000 ms
- 14:30:02.200 → Silence for 200 ms
- 14:30:02.400 → Transmitter 2 active for 1000 ms
- 14:30:03.400 → Silence for 200 ms
- 14:30:03.600 → Cycle repeats starting at Transmitter 0

## Prerequisites 📋

- GNU Radio installed
- NTP client installed and configured (chrony recommended)
- Network access to NTP servers
- Proper system time setup

## Installation 🚀

1. In the `gr-selector` directory, run:

```bash
mkdir build
cd build
cmake ../
make
sudo make install
sudo ldconfig
```

2. Verify the block appears in GNU Radio Companion under the `[selector]` category as **Multiselector NTP Samples Scheduled**.

## Example Usage 💻

In your `.grc` file:

```python
selector.multiselector_ntp_samples_scheduled(
    num_outputs=3,
    switch_period_ms=1000,
    switch_delay_ms=500,
    samp_rate=2.4e6,
    ntp_start_time_str="14:30:00",
    ntp_servers="time.google.com,pool.ntp.org",
    sync_interval=60
)
```

## Runtime API Methods 🔧

- `set_ntp_start_time(time_str)`: Set a new NTP start time (format: HH:MM:SS)
- `force_ntp_sync()`: Force immediate NTP synchronization
- `get_ntp_status()`: Return NTP synchronization status, offset, and parameters
- `set_samp_rate(rate)`: Change sample rate
- `set_switch_period_ms(ms)`: Change active transmission period
- `set_switch_delay_ms(ms)`: Change silence period duration

## Use Cases 🎯

This block is ideal for applications requiring coordinated transmission cycles with strict timing, such as:

- Multi-antenna systems
- Synchronized RF networks
- Time-division multiple access (TDMA) systems
- Coordinated spectrum sensing

## License 📄

This project is licensed under the MIT License - see below for details:

## Contact 📬

For questions or contributions, please open an issue in this GitHub repository or contact the developer directly.

---
