import wave
import struct
import math

def generate_tone(filename, freq1, freq2, duration, sample_rate=44100, volume=0.5):
    with wave.open(filename, 'w') as wav_file:
        wav_file.setnchannels(1) # Mono
        wav_file.setsampwidth(2) # 16-bit
        wav_file.setframerate(sample_rate)
        
        num_samples = int(duration * sample_rate)
        
        for i in range(num_samples):
            time = i / sample_rate
            # Alternate between freq1 and freq2 every 0.25 seconds (for scram) and 0.5s (for lofa)
            if freq2 == 0:
                freq = freq1 if (time % 1.0) < 0.5 else freq2 # LOFA: 0.5s beep, 0.5s silence
            else:
                freq = freq1 if (time % 0.2) < 0.1 else freq2 # SCRAM: fast siren
            
            value = 0 if freq == 0 else int(volume * 32767.0 * math.sin(2 * math.pi * freq * time))
            data = struct.pack('<h', value)
            wav_file.writeframesraw(data)

# SCRAM: Fast alternating high-pitch siren (800 Hz and 1200 Hz)
generate_tone('scram_alarm.wav', 800, 1200, 3.0, volume=0.8)

# LOFA: Slow warning beep (500 Hz and 0 Hz/Silence)
generate_tone('lofa_alarm.wav', 500, 0, 3.0, volume=0.8)

print("Generated WAV files.")
