# Pair a device

This page pairs another Echo with the bridge, or pairs one again after `hal-echo unpair`. Pairing
pins each side's certificate; it is needed once per device.

## Steps

1. Start pairing on the PC, choosing the device's mode ([Modes](../user/modes.md)).

   ```bash
   hal-echo pair --mode personal    # listens for five minutes, or until one device pairs
   ```

2. On the Echo, hold the eye for two seconds, tap **Pair with a PC**, and wait for "Found".

3. Type the six digits the Echo shows into the PC's prompt. Check the device name and address
   the PC prints first: a request you did not start is someone else's, so press Enter on an empty
   line to refuse it.

4. Check the result.

   ```bash
   hal-echo devices                 # the new device is listed and, a moment later, online
   ```

## Symptoms and fixes

| Symptom | Fix |
| --- | --- |
| `hal-echo pair` says port 47801 is in use | Another `hal-echo pair` is running; stop it. |
| The Echo never says "Found" | mDNS is blocked: type the PC's address on the pairing screen. |
| "No device paired" after three tries | Three wrong codes end pairing; start `hal-echo pair` again. |
| The device pairs but stays offline | Allow its address through the firewall: `hal-echo firewall`. |
