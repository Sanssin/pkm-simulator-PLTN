#include <Servo.h>

const int SERVO_PIN = 9; // Pin sinyal servo (kabel oranye/kuning dicolok ke Pin D9)
Servo myServo;

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(9600); // Pastikan Serial Monitor diatur ke 9600 baud

  myServo.attach(SERVO_PIN);
  myServo.write(0); // Posisi awal 0% (0 derajat)

  Serial.println(F("========================================"));
  Serial.println(F("    TESTER SERVO UMUM (PERSENTASE 0-100%)"));
  Serial.println(F("========================================"));
  Serial.println(F("Ketik angka 0 sampai 100 lalu tekan Enter."));
  Serial.println(F("Contoh: ketik 85 lalu Enter -> bergerak ke 85%"));
  Serial.print(F("Pin Servo Aktif: Pin D"));
  Serial.println(SERVO_PIN);
  Serial.println(F("----------------------------------------"));
  Serial.print(F("Masukkan persen (0-100): "));
}

void loop() {
  if (Serial.available() > 0) {
    // Buang karakter spasi atau enter di awal
    char c = Serial.peek();
    if (!isDigit(c)) {
      Serial.read();
      return;
    }

    int percent = Serial.parseInt();

    // Bersihkan buffer sisa karakter
    while (Serial.available() > 0) {
      Serial.read();
    }

    if (percent >= 0 && percent <= 100) {
      // shortcut: pemetaan linear 0-100% ke 0-180 derajat, ubah 180 jika batas maket berbeda
      int angle = map(percent, 0, 100, 0, 180);

      digitalWrite(LED_BUILTIN, HIGH);
      myServo.write(angle);

      Serial.print(F("\n[OK] Input: "));
      Serial.print(percent);
      Serial.print(F("% -> Mengarahkan ke "));
      Serial.print(angle);
      Serial.println(F(" derajat."));

      delay(150);
      digitalWrite(LED_BUILTIN, LOW);
    } else {
      Serial.print(F("\n[ERROR] Nilai "));
      Serial.print(percent);
      Serial.println(F(" tidak valid! Masukkan angka antara 0 sampai 100."));
    }

    Serial.print(F("Masukkan persen (0-100): "));
  }
}
