import numpy as np
from gnuradio import gr
import time
import threading
import subprocess
import re
import socket
import struct

class multiselector_ntp_samples_scheduled(gr.sync_block):
    """
    Cyclically selects outputs based on sample count with NTP synchronized start:
    - for switch_period_ms sends signal to outX (X=0..num_outputs-1)
    - for switch_delay_ms sends signal to outDelay (index = num_outputs)
    - starts transmission at specified NTP time
    - uses sample count for hardware precision
    """
    def __init__(self, num_outputs=3, switch_period_ms=1000, switch_delay_ms=500,
                 samp_rate=2.4e6, ntp_start_time_str="", ntp_servers=None, sync_interval=60):
        total_outputs = num_outputs + 1

        gr.sync_block.__init__(
            self,
            name="multiselector_ntp_samples_scheduled",
            in_sig=[np.complex64],
            out_sig=[np.complex64] * total_outputs
        )

        # Parameters
        self.num_active_outputs = int(num_outputs)
        self.total_outputs = int(total_outputs)
        self.silence_output_index = int(num_outputs)
        self.switch_period_ms = float(switch_period_ms)
        self.switch_delay_ms = float(switch_delay_ms)
        self.samp_rate = float(samp_rate)
        self.sync_interval = float(sync_interval)

        # Internal state
        self.sample_count = 0                  # absolute count of processed samples
        self.current_output = 0
        self.phase = "waiting"                 # "waiting", "active", "silence"
        self.samples_per_period = 0
        self.samples_per_delay = 0
        self.transmission_started = False
        self.start_sample = None

        # Local phase progress (to avoid ambiguity with modulo on sample_count)
        self.phase_progress = 0                # samples elapsed in current phase

        # Recalculate samples per period/delay
        self._recalculate_timing()

        # NTP servers
        if ntp_servers is None or ntp_servers == "" or ntp_servers == '""':
            self.ntp_servers = [
                "time.google.com",
                "pool.ntp.org",
                "time.cloudflare.com",
                "time.nist.gov"
            ]
        elif isinstance(ntp_servers, str):
            self.ntp_servers = [s.strip() for s in ntp_servers.split(',') if s.strip()]
        else:
            self.ntp_servers = ntp_servers

        # NTP synchronization state
        self.ntp_offset = 0.0
        self.ntp_synchronized = False
        self.last_ntp_sync = 0.0
        self.ntp_lock = threading.Lock()

        # Event to stop thread cleanly
        self._stop_event = threading.Event()

        # Start initial NTP synchronization (non-blocking if it fails)
        print("Initial NTP synchronization in progress...")
        try:
            success = self._sync_with_ntp()
            if success:
                print("Initial NTP synchronization completed")
            else:
                print("WARNING: Initial NTP synchronization failed, using system time")
        except Exception as e:
            print(f"Error during initial sync: {e}")

        # Start periodic synchronization thread
        self._start_ntp_sync_thread()

        # Calculate start time: if provided use parse, otherwise next minute (based on _get_ntp_time())
        if ntp_start_time_str:
            self.start_time = self._parse_ntp_start_time(ntp_start_time_str)
        else:
            current_ntp = self._get_ntp_time()
            self.start_time = self._calculate_next_minute(current_ntp)

        self._print_initialization_info()

    def _recalculate_timing(self):
        """Recalculates samples based on current sample rate"""
        # Avoid zero
        if self.samp_rate <= 0:
            raise ValueError("samp_rate must be > 0")
        self.samples_per_period = max(1, int((self.switch_period_ms / 1000.0) * self.samp_rate))
        self.samples_per_delay = max(1, int((self.switch_delay_ms / 1000.0) * self.samp_rate))
        print(f"Timing updated: period={self.samples_per_period} samples, delay={self.samples_per_delay} samples")

    # -------------------
    # NTP / synchronization
    # -------------------
    def _start_ntp_sync_thread(self):
        """Starts thread for periodic NTP synchronization."""
        self.ntp_thread = threading.Thread(target=self._ntp_sync_worker, daemon=True)
        self.ntp_thread.start()

    def _ntp_sync_worker(self):
        """Worker thread that maintains NTP synchronization."""
        print("NTP sync worker started.")
        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                if current_time - self.last_ntp_sync >= self.sync_interval:
                    success = self._sync_with_ntp()
                    if success:
                        with self.ntp_lock:
                            self.last_ntp_sync = current_time
                            self.ntp_synchronized = True
                        print(f"[NTP] Sync performed: offset {self.ntp_offset*1000:.3f} ms")
                    else:
                        with self.ntp_lock:
                            self.ntp_synchronized = False
                        print("[NTP] Sync failed")
                # waits a short interval to respond to stop_event
                self._stop_event.wait(10)
            except Exception as e:
                print(f"Error in NTP synchronization: {e}")
                with self.ntp_lock:
                    self.ntp_synchronized = False
                # waits before retrying
                self._stop_event.wait(30)
        print("NTP sync worker terminated.")

    def _sync_with_ntp(self):
        """Synchronizes with NTP server and calculates offset using chrony."""

        offset = self._sync_with_chrony()
        if offset is not None:
            with self.ntp_lock:
                self.ntp_offset = offset
            return True

    def _sync_with_chrony(self):
        """Uses chronyc sources -v to get NTP offset (more robust parsing with regex)."""
        try:
            result = subprocess.run(['chronyc', 'sources', '-v'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout:
                lines = result.stdout.splitlines()
                for line in lines:
                    # consider only lines with '*' or '+' (current/combined)
                    if '*' in line or '+' in line:
                        # search for any number followed by unit (ms/us/ns)
                        m = re.search(r'([-+]?\d+(?:\.\d+)?)(ms|us|ns)\b', line)
                        if m:
                            val = float(m.group(1))
                            unit = m.group(2)
                            if unit == 'ms':
                                return val / 1000.0
                            elif unit == 'us':
                                return val / 1_000_000.0
                            elif unit == 'ns':
                                return val / 1_000_000_000.0
                        else:
                            # fallback: search for value in seconds (decimal)
                            m2 = re.search(r'offset\s+([-+]?\d+(?:\.\d+)?)', line)
                            if m2:
                                return float(m2.group(1))
        except FileNotFoundError:
            pass
        except subprocess.TimeoutExpired:
            pass
        except Exception as e:
            print(f"Error parsing chronyc: {e}")
        return None

    def _get_ntp_time(self):
        """Gets current NTP time (system time + NTP offset)."""
        with self.ntp_lock:
            system_time = time.time()
            ntp_time = system_time + self.ntp_offset
            return ntp_time

    def _parse_ntp_start_time(self, time_str):
        """Converts "HH:MM:SS" string to next corresponding NTP timestamp."""
        try:
            hours, minutes, seconds = map(int, time_str.split(':'))
            current_ntp = self._get_ntp_time()
            # calculate struct time in local timezone based on current_ntp
            current_struct = time.localtime(current_ntp)

            # build target for today (in epoch seconds, local)
            today_target_struct = time.struct_time((
                current_struct.tm_year,
                current_struct.tm_mon,
                current_struct.tm_mday,
                hours, minutes, seconds,
                0, 0, -1
            ))
            today_target = time.mktime(today_target_struct)

            # Don't add offset here: _get_ntp_time() already includes offset in comparison
            if today_target <= current_ntp:
                today_target += 24 * 3600

            return today_target
        except Exception as e:
            print(f"Invalid time format: {time_str}. Use HH:MM:SS ({e})")
            return self._calculate_next_minute(self._get_ntp_time())

    def _calculate_next_minute(self, timestamp):
        """Calculates timestamp of next minute relative to provided timestamp."""
        time_struct = time.localtime(timestamp)
        next_minute = int(timestamp) + (60 - time_struct.tm_sec)
        return next_minute

    # -------------------
    # work / main logic
    # -------------------
    def work(self, input_items, output_items):
        in0 = input_items[0]
        noutput_items = len(in0)

        # Zero all outputs (safety)
        for i in range(self.total_outputs):
            output_items[i][:] = np.zeros_like(in0)

        # If waiting for start time
        if self.phase == "waiting":
            current_ntp = self._get_ntp_time()
            if current_ntp >= self.start_time:
                # Time to start!
                self.phase = "active"
                self.sample_count = 0
                self.phase_progress = 0
                self.current_output = 0
                self.transmission_started = True

                ntp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_ntp))
                sync_status = "SYNC" if self.ntp_synchronized else "NO SYNC"
                print(f"Transmission started at: {ntp_str} NTP ({sync_status})")
                print(f"Current NTP offset: {self.ntp_offset*1000:.1f} ms")
            else:
                # Not time yet, don't transmit
                return noutput_items

        # Processing based on sample count using local phase progress
        start_idx = 0
        while start_idx < noutput_items:
            remaining_items = noutput_items - start_idx

            if self.phase == "active":
                # how many samples needed to complete current active phase
                need = self.samples_per_period - self.phase_progress
                process_len = min(need, remaining_items)

                end_idx = start_idx + process_len
                # Copy input to current output
                output_items[self.current_output][start_idx:end_idx] = in0[start_idx:end_idx]

                # update counters
                self.phase_progress += process_len
                self.sample_count += process_len
                start_idx += process_len

                # if active phase is finished
                if self.phase_progress >= self.samples_per_period:
                    # switch to silence
                    self.phase = "silence"
                    self.phase_progress = 0
                    # NOTE: don't increment current_output here, we'll do it at end of silence cycle

            elif self.phase == "silence":
                # how many samples needed to complete current silence delay
                need = self.samples_per_delay - self.phase_progress
                process_len = min(need, remaining_items)

                end_idx = start_idx + process_len
                # In silence channel don't copy data: leave zero (already zeroed above)
                # (but for clarity we can re-assign zeros)
                output_items[self.silence_output_index][start_idx:end_idx] = np.zeros(process_len, dtype=in0.dtype)

                # update counters
                self.phase_progress += process_len
                self.sample_count += process_len
                start_idx += process_len

                # if silence phase is finished
                if self.phase_progress >= self.samples_per_delay:
                    self.phase = "active"
                    self.phase_progress = 0
                    # Advance to next transmitter
                    self.current_output = (self.current_output + 1) % self.num_active_outputs

            else:
                # unexpected state: ensure return to active for safety
                print(f"Unexpected phase state: {self.phase}, forced to 'active'")
                self.phase = "active"
                self.phase_progress = 0

        return noutput_items

    # -------------------
    # Info / runtime api
    # -------------------
    def _print_initialization_info(self):
        sync_status = "SYNCHRONIZED" if self.ntp_synchronized else "NOT SYNCHRONIZED"
        start_ntp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.start_time))

        print(f"Multiselector NTP configured:")
        print(f"- Active transmitters: {self.num_active_outputs}")
        print(f"- Total outputs: {self.total_outputs} ({self.num_active_outputs} transmitters + 1 silence)")
        print(f"- Sample rate: {self.samp_rate/1e6:.2f} MHz")
        print(f"- Transmitter period: {self.switch_period_ms} ms ({self.samples_per_period} samples)")
        print(f"- Silence period: {self.switch_delay_ms} ms ({self.samples_per_delay} samples)")
        print(f"- NTP servers: {', '.join(self.ntp_servers[:3])}...")
        print(f"- Sync interval: {self.sync_interval} s")
        print(f"- NTP status: {sync_status}")
        print(f"- NTP offset: {self.ntp_offset*1000:.1f} ms")
        print(f"- NTP transmission start: {start_ntp_str}")

    def set_samp_rate(self, samp_rate):
        """Changes sample rate and recalculates timings"""
        self.samp_rate = float(samp_rate)
        self._recalculate_timing()

    def set_switch_period_ms(self, new_value):
        """Changes active phase duration and recalculates samples."""
        self.switch_period_ms = float(new_value)
        self._recalculate_timing()

    def set_switch_delay_ms(self, new_value):
        """Changes delay phase duration and recalculates samples."""
        self.switch_delay_ms = float(new_value)
        self._recalculate_timing()

    def set_ntp_start_time(self, time_str):
        """Sets new start time in HH:MM:SS format."""
        self.start_time = self._parse_ntp_start_time(time_str)
        self.phase = "waiting"
        self.transmission_started = False
        start_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.start_time))
        print(f"New NTP start time: {start_str}")

    def force_ntp_sync(self):
        """Forces immediate NTP synchronization."""
        success = self._sync_with_ntp()
        if success:
            print(f"NTP synchronization completed. Offset: {self.ntp_offset*1000:.1f} ms")
            return True
        else:
            print("NTP synchronization failed")
            return False

    def get_ntp_status(self):
        """Returns NTP synchronization status."""
        with self.ntp_lock:
            return {
                'synchronized': self.ntp_synchronized,
                'offset_ms': self.ntp_offset * 1000,
                'ntp_time': self._get_ntp_time(),
                'system_time': time.time(),
                'last_sync_ago': time.time() - self.last_ntp_sync,
                'servers': self.ntp_servers,
                'sample_count': self.sample_count,
                'phase': self.phase,
                'current_output': self.current_output
            }

    def get_switch_period_ms(self):
        return self.switch_period_ms

    def get_switch_delay_ms(self):
        return self.switch_delay_ms

    # -------------------
    # Stop / cleanup
    # -------------------
    def stop(self):
        """Called when flowgraph stops: stops NTP thread cleanly."""
        print("Block stop: stopping NTP worker...")
        self._stop_event.set()
        if hasattr(self, 'ntp_thread') and self.ntp_thread.is_alive():
            self.ntp_thread.join(timeout=5)
        print("NTP worker stopped.")
        return True

    def __del__(self):
        try:
            self._stop_event.set()
        except Exception:
            pass
