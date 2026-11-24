package com.s5mod.unlocker;

import android.app.Activity;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.hardware.usb.UsbConstants;
import android.hardware.usb.UsbDevice;
import android.hardware.usb.UsbDeviceConnection;
import android.hardware.usb.UsbEndpoint;
import android.hardware.usb.UsbInterface;
import android.hardware.usb.UsbManager;
import android.os.Build;
import android.os.Bundle;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.Window;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.HashMap;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final int VID = 0x04DA;
    private static final int PID = 0x2370;
    private static final int TIMEOUT_MS = 4000;
    private static final String ACTION_USB_PERMISSION = "com.s5mod.unlocker.USB_PERMISSION";

    // Baxter family interface language — draft 2 (2026-10-21)
    private static final int C_GROUND  = 0xFF0E0E0E;
    private static final int C_WELL    = 0xFF141414;
    private static final int C_SURFACE = 0xFF151515;
    private static final int C_PANEL   = 0xFF1E1E1E;
    private static final int C_HOVER   = 0xFF242424;
    private static final int C_OPEN    = 0xFF2D2D2D;
    private static final int C_ON      = 0xFF3A3A3A;
    private static final int C_PRESSED = 0xFF525252;
    private static final int C_EDGE    = 0xFF717171;
    private static final int C_DIM     = 0xFF989898;
    private static final int C_LIGHT   = 0xFFC1C1C1;
    private static final int C_NEEDLE  = 0xFFE8E8E8;
    private static final int C_SIGNAL  = 0xFFB8212F; // Signal crimson — live/armed only

    private enum UiState { WAITING, READY, ARMED }

    // MC801 FW 2.9 signature anchors: {addr, allowed1, allowed2 (-1 if only 1)}
    private static final int[][] SIG_CHECKS = {
        {0x866B493A, 0x2801, -1},
        {0x866B493E, 0xB2E0, -1},
        {0x866B4952, 0x486B, -1},
        {0x866B4956, 0xBD10, -1},
        {0x86F15E8C, 0x00CE, -1},
        {0x86F15E98, 0xFFFF, -1},
        {0x87089604, 0x00CE, -1},
        {0x87089634, 0xFFFF, -1},
        {0x08A68C4C, 0x00CE, -1},
        {0x08A6844C, 0x00CE, -1},
        {0x868261B4, 0x460D, -1},
        {0x868261B6, 0x4628, 0x2000},
        {0x868261B8, 0xE8BD, -1},
    };

    // Volatile RAM patches: {addr, unlockVal, stockVal}
    // Survives power-switch OFF/ON (suspend-to-RAM) until battery removal.
    private static final int[][] PATCHES = {
        // 1) NTSC Validator Whitelist (0x86F15E30 tail)
        {0x86F15E90, 0x00F1, 0x00D1},
        {0x86F15E92, 0x80F1, 0x80D1},
        {0x86F15E94, 0x00ED, 0x00D2},
        {0x86F15E96, 0x80ED, 0x80D2},

        // 2) Master ROM-in-RAM MOV Template (0x87089524 tail — survives soft power-off/on!)
        {0x87089614, 0x00F1, 0x00D1},
        {0x8708961C, 0x80F1, 0x80D1},
        {0x87089624, 0x00ED, 0x00D2},
        {0x8708962C, 0x80ED, 0x80D2},

        // 3) Active NTSC MOV Source Template (0x08A68B6C tail)
        {0x08A68C5C, 0x00F1, 0x00D1},
        {0x08A68C64, 0x80F1, 0x80D1},
        {0x08A68C6C, 0x00ED, 0x00D2},
        {0x08A68C74, 0x80ED, 0x80D2},

        // 4) Live UI Menu Table (0x08A6836C tail, visibility=0x0104)
        {0x08A6845C, 0x00F1, 0x00D1},
        {0x08A6845E, 0x0104, 0x0104},
        {0x08A68464, 0x80F1, 0x80D1},
        {0x08A6846C, 0x00ED, 0x00D2},
        {0x08A6846E, 0x0104, 0x0104},
        {0x08A68474, 0x80ED, 0x80D2},

        // 5) Unlimited recording in ALL limited modes (0x86826102 returns 0)
        {0x868261B6, 0x2000, 0x4628},
    };

    private UsbManager usbManager;
    private UsbDevice currentDevice;
    private UsbDeviceConnection conn;
    private UsbInterface usbIf;
    private UsbEndpoint epOut;
    private UsbEndpoint epIn;
    private boolean busy = false;
    private boolean isUnlocked = false;
    private boolean logExpanded = false;
    private UiState uiState = UiState.WAITING;

    // Header
    private View statusDot;
    private TextView statusLabel;

    // 3 state containers (nothing the moment doesn't need)
    private LinearLayout viewWaiting;
    private LinearLayout viewReady;
    private LinearLayout viewArmed;

    // Interactive controls
    private Button btnConnect;
    private Button btnUnlock;
    private Button btnRestore;
    private TextView readySubNote;
    private TextView armedHeadline;
    private TextView waitingHint;

    // Collapsible log drawer (shared across Ready & Armed)
    private LinearLayout logBar;
    private TextView logBarTitle;
    private TextView logBarToggle;
    private ScrollView logScroll;
    private TextView logView;

    private final BroadcastReceiver usbReceiver = new BroadcastReceiver() {
        @Override
        public void onReceive(Context context, Intent intent) {
            String action = intent.getAction();
            if (ACTION_USB_PERMISSION.equals(action)) {
                UsbDevice dev = getUsbDeviceExtra(intent);
                if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false) && dev != null) {
                    openAndVerifyAsync(dev);
                } else {
                    appendLog("usb permission denied");
                    showHeaderStatus("Permission denied", C_EDGE, C_DIM);
                }
            } else if (UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(action)) {
                UsbDevice dev = getUsbDeviceExtra(intent);
                if (dev != null && dev.getVendorId() == VID && dev.getProductId() == PID) {
                    connectDevice(dev);
                }
            } else if (UsbManager.ACTION_USB_DEVICE_DETACHED.equals(action)) {
                UsbDevice dev = getUsbDeviceExtra(intent);
                if (dev != null && currentDevice != null && dev.getDeviceId() == currentDevice.getDeviceId()) {
                    closeUsb();
                    appendLog("camera unplugged");
                    if (isUnlocked) {
                        runOnUiThread(() -> {
                            armedHeadline.setText("Camera unplugged · armed");
                            btnRestore.setVisibility(View.GONE);
                            showHeaderStatus("Armed", C_SIGNAL, C_NEEDLE);
                        });
                    } else {
                        setUiState(UiState.WAITING, "Waiting");
                    }
                }
            }
        }
    };

    @SuppressWarnings("deprecation")
    private UsbDevice getUsbDeviceExtra(Intent intent) {
        if (Build.VERSION.SDK_INT >= 33) {
            return intent.getParcelableExtra(UsbManager.EXTRA_DEVICE, UsbDevice.class);
        }
        return intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);
    }

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Window w = getWindow();
        w.setStatusBarColor(C_PANEL);
        w.setNavigationBarColor(C_GROUND);

        usbManager = (UsbManager) getSystemService(Context.USB_SERVICE);
        buildUi();

        IntentFilter filter = new IntentFilter();
        filter.addAction(ACTION_USB_PERMISSION);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_ATTACHED);
        filter.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(usbReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(usbReceiver, filter);
        }

        handleIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        handleIntent(intent);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        try { unregisterReceiver(usbReceiver); } catch (Exception ignored) {}
        closeUsb();
    }

    private void handleIntent(Intent intent) {
        if (intent != null && UsbManager.ACTION_USB_DEVICE_ATTACHED.equals(intent.getAction())) {
            UsbDevice dev = getUsbDeviceExtra(intent);
            if (dev != null && dev.getVendorId() == VID && dev.getProductId() == PID) {
                connectDevice(dev);
                return;
            }
        }
        UsbDevice found = findS5();
        if (found != null) {
            connectDevice(found);
        }
    }

    private int dp(int v) {
        return (int) TypedValue.applyDimension(
                TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    private GradientDrawable box(int fill, int stroke, int radiusDp) {
        GradientDrawable d = new GradientDrawable();
        d.setColor(fill);
        d.setCornerRadius(dp(radiusDp));
        if (stroke != 0) d.setStroke(dp(1), stroke);
        return d;
    }

    /** Crisp 3:2 Open Gate sensor reticle (matches DIETER board & app icon). */
    private class ReticleView extends View {
        private final boolean armed;
        private final Paint framePaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint tickPaint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final Paint dotPaint = new Paint(Paint.ANTI_ALIAS_FLAG);

        ReticleView(Context ctx, boolean armed) {
            super(ctx);
            this.armed = armed;
            framePaint.setStyle(Paint.Style.STROKE);
            framePaint.setStrokeWidth(dp(1) * 1.5f);
            framePaint.setColor(armed ? C_LIGHT : C_OPEN);

            tickPaint.setStyle(Paint.Style.STROKE);
            tickPaint.setStrokeWidth(dp(1));
            tickPaint.setColor(armed ? C_PRESSED : C_HOVER);

            dotPaint.setStyle(Paint.Style.FILL);
            dotPaint.setColor(C_SIGNAL);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            float w = dp(136);
            float h = dp(90); // 3:2
            float x = (getWidth() - w) / 2f;
            float y = (getHeight() - h) / 2f;
            float r = dp(3);
            canvas.drawRoundRect(new RectF(x, y, x + w, y + h), r, r, framePaint);

            // Subtle 16:9 crop tick marks
            float tIn = dp(8);
            float tLen = dp(10);
            float tOff = dp(14);
            canvas.drawLine(x + tIn, y + tOff, x + tIn + tLen, y + tOff, tickPaint);
            canvas.drawLine(x + w - tIn - tLen, y + tOff, x + w - tIn, y + tOff, tickPaint);
            canvas.drawLine(x + tIn, y + h - tOff, x + tIn + tLen, y + h - tOff, tickPaint);
            canvas.drawLine(x + w - tIn - tLen, y + h - tOff, x + w - tIn, y + h - tOff, tickPaint);

            float cx = getWidth() / 2f;
            float cy = getHeight() / 2f;
            if (armed) {
                canvas.drawCircle(cx, cy, dp(6), dotPaint);
            } else {
                Paint cross = new Paint(Paint.ANTI_ALIAS_FLAG);
                cross.setColor(C_ON);
                cross.setStrokeWidth(dp(1));
                float arm = dp(6);
                canvas.drawLine(cx - arm, cy, cx + arm, cy, cross);
                canvas.drawLine(cx, cy - arm, cx, cy + arm, cross);
            }
        }
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(C_GROUND);

        // ── Header row (edge-to-edge #1E1E1E) ──
        LinearLayout header = new LinearLayout(this);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.setBackgroundColor(C_PANEL);
        header.setPadding(dp(20), dp(22), dp(20), dp(18));

        TextView title = new TextView(this);
        title.setText("S5 Unlocker");
        title.setTextColor(C_NEEDLE);
        title.setTextSize(20);
        title.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        title.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f));
        header.addView(title);

        LinearLayout sigGroup = new LinearLayout(this);
        sigGroup.setOrientation(LinearLayout.HORIZONTAL);
        sigGroup.setGravity(Gravity.CENTER_VERTICAL);

        statusDot = new View(this);
        LinearLayout.LayoutParams dotLp = new LinearLayout.LayoutParams(dp(8), dp(8));
        dotLp.rightMargin = dp(8);
        statusDot.setLayoutParams(dotLp);
        statusDot.setBackground(box(C_EDGE, 0, 4));
        sigGroup.addView(statusDot);

        statusLabel = new TextView(this);
        statusLabel.setText("Waiting");
        statusLabel.setTextColor(C_DIM);
        statusLabel.setTextSize(13);
        sigGroup.addView(statusLabel);

        header.addView(sigGroup);
        root.addView(header);

        // ── Main content area (holds whichever of the 3 states is active) ──
        LinearLayout stage = new LinearLayout(this);
        stage.setOrientation(LinearLayout.VERTICAL);
        stage.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f));

        viewWaiting = buildWaitingView();
        viewReady = buildReadyView();
        viewArmed = buildArmedView();

        stage.addView(viewWaiting);
        stage.addView(viewReady);
        stage.addView(viewArmed);
        root.addView(stage);

        // ── Collapsible session log footer (visible in Ready & Armed) ──
        logBar = new LinearLayout(this);
        logBar.setOrientation(LinearLayout.VERTICAL);
        logBar.setBackgroundColor(C_GROUND);
        logBar.setPadding(dp(20), dp(0), dp(20), dp(20));

        LinearLayout logToggleRow = new LinearLayout(this);
        logToggleRow.setOrientation(LinearLayout.HORIZONTAL);
        logToggleRow.setGravity(Gravity.CENTER_VERTICAL);
        logToggleRow.setBackground(box(C_WELL, C_HOVER, 6));
        logToggleRow.setPadding(dp(12), dp(10), dp(12), dp(10));
        logToggleRow.setOnClickListener(v -> toggleLog());

        logBarTitle = new TextView(this);
        logBarTitle.setText("Session log");
        logBarTitle.setTextColor(C_DIM);
        logBarTitle.setTextSize(11);
        logBarTitle.setTypeface(Typeface.MONOSPACE);
        logBarTitle.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f));
        logToggleRow.addView(logBarTitle);

        logBarToggle = new TextView(this);
        logBarToggle.setText("Show \u25BE");
        logBarToggle.setTextColor(C_EDGE);
        logBarToggle.setTextSize(11);
        logToggleRow.addView(logBarToggle);
        logBar.addView(logToggleRow);

        logScroll = new ScrollView(this);
        logScroll.setBackground(box(C_WELL, C_HOVER, 6));
        logScroll.setPadding(dp(12), dp(10), dp(12), dp(10));
        LinearLayout.LayoutParams lsLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(128));
        lsLp.topMargin = dp(6);
        logScroll.setLayoutParams(lsLp);
        logScroll.setVisibility(View.GONE);

        logView = new TextView(this);
        logView.setText("ready");
        logView.setTextColor(C_DIM);
        logView.setTextSize(11);
        logView.setLineSpacing(dp(2), 1.0f);
        logView.setTypeface(Typeface.MONOSPACE);
        logScroll.addView(logView);
        logBar.addView(logScroll);

        root.addView(logBar);

        setContentView(root);
        applyUiState();
    }

    private LinearLayout buildWaitingView() {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT));

        // Calm centered stage
        LinearLayout center = new LinearLayout(this);
        center.setOrientation(LinearLayout.VERTICAL);
        center.setGravity(Gravity.CENTER);
        center.setPadding(dp(24), dp(24), dp(24), dp(24));
        center.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, 0, 1.0f));

        ReticleView reticle = new ReticleView(this, false);
        reticle.setLayoutParams(new LinearLayout.LayoutParams(dp(160), dp(104)));
        center.addView(reticle);

        TextView cap = new TextView(this);
        cap.setText("04DA:2370 \u00B7 SERVICE MODE");
        cap.setTextColor(C_EDGE);
        cap.setTextSize(10);
        cap.setTypeface(Typeface.MONOSPACE);
        cap.setGravity(Gravity.CENTER);
        cap.setPadding(0, dp(10), 0, dp(36));
        center.addView(cap);

        TextView line1 = new TextView(this);
        line1.setText("Hold Playback + AF/AE Lock and power on");
        line1.setTextColor(C_LIGHT);
        line1.setTextSize(13);
        line1.setGravity(Gravity.CENTER);
        center.addView(line1);

        waitingHint = new TextView(this);
        waitingHint.setText("Plug in USB-C cable \u2014 app opens automatically");
        waitingHint.setTextColor(C_DIM);
        waitingHint.setTextSize(11);
        waitingHint.setGravity(Gravity.CENTER);
        waitingHint.setPadding(0, dp(6), 0, 0);
        center.addView(waitingHint);

        wrap.addView(center);

        // Bottom edge-to-edge surface shelf (#151515)
        LinearLayout shelf = new LinearLayout(this);
        shelf.setOrientation(LinearLayout.VERTICAL);
        shelf.setBackgroundColor(C_SURFACE);
        shelf.setPadding(dp(20), dp(22), dp(20), dp(22));

        btnConnect = makeButton("Connect USB", C_HOVER, C_LIGHT, 14, 15);
        btnConnect.setOnClickListener(v -> {
            UsbDevice dev = findS5();
            if (dev == null) {
                waitingHint.setText("No DC-S5 detected yet \u2014 check USB-C cable");
                appendLog("no camera on usb");
            } else {
                connectDevice(dev);
            }
        });
        shelf.addView(btnConnect);

        wrap.addView(shelf);
        return wrap;
    }

    private LinearLayout buildReadyView() {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT));

        // Surface band (#151515): value wells + 4 clean spec rows
        LinearLayout surface = new LinearLayout(this);
        surface.setOrientation(LinearLayout.VERTICAL);
        surface.setBackgroundColor(C_SURFACE);
        surface.setPadding(dp(20), dp(20), dp(20), dp(22));

        LinearLayout wellRow = new LinearLayout(this);
        wellRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams wrLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        wrLp.bottomMargin = dp(24);
        wellRow.setLayoutParams(wrLp);
        addWell(wellRow, "Firmware", "MC801 2.9", true);
        addWell(wellRow, "State", "Stock", false);
        surface.addView(wellRow);

        TextView heading = new TextView(this);
        heading.setText("Modes to enable");
        heading.setTextColor(C_NEEDLE);
        heading.setTextSize(15);
        heading.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        heading.setPadding(0, 0, 0, dp(12));
        surface.addView(heading);

        addSpecRow(surface, "6K Open Gate", "5952\u00D73968 \u00B7 23.98p \u00B7 10-bit", C_LIGHT, C_DIM);
        addSpecRow(surface, "5.9K Full", "5888\u00D73312 \u00B7 23.98p \u00B7 10-bit", C_LIGHT, C_DIM);
        addSpecRow(surface, "Recording limit", "Unlimited \u00B7 all modes", C_LIGHT, C_DIM);
        addSpecRow(surface, "Power switch", "Survives until battery pull", C_LIGHT, C_DIM);

        wrap.addView(surface);

        // Ground action stage (#0E0E0E)
        LinearLayout action = new LinearLayout(this);
        action.setOrientation(LinearLayout.VERTICAL);
        action.setPadding(dp(20), dp(28), dp(20), dp(16));

        btnUnlock = makeButton("Unlock camera", C_PRESSED, C_NEEDLE, 15, 17);
        btnUnlock.setOnClickListener(v -> applyAllAsync(true));
        action.addView(btnUnlock);

        readySubNote = new TextView(this);
        readySubNote.setText("13 signatures verified \u00B7 19 RAM words");
        readySubNote.setTextColor(C_DIM);
        readySubNote.setTextSize(11);
        readySubNote.setTypeface(Typeface.MONOSPACE);
        readySubNote.setGravity(Gravity.CENTER);
        readySubNote.setPadding(0, dp(14), 0, 0);
        action.addView(readySubNote);

        wrap.addView(action);
        return wrap;
    }

    private LinearLayout buildArmedView() {
        LinearLayout wrap = new LinearLayout(this);
        wrap.setOrientation(LinearLayout.VERTICAL);
        wrap.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.MATCH_PARENT));

        // Lit 3:2 Open Gate reticle with crimson dot on #0E0E0E ground
        LinearLayout hero = new LinearLayout(this);
        hero.setOrientation(LinearLayout.VERTICAL);
        hero.setGravity(Gravity.CENTER);
        hero.setPadding(dp(20), dp(24), dp(20), dp(20));

        ReticleView reticle = new ReticleView(this, true);
        reticle.setLayoutParams(new LinearLayout.LayoutParams(dp(160), dp(104)));
        hero.addView(reticle);

        TextView cap = new TextView(this);
        cap.setText("5952 \u00D7 3968 \u00B7 3:2 OPEN GATE");
        cap.setTextColor(C_DIM);
        cap.setTextSize(10);
        cap.setTypeface(Typeface.MONOSPACE);
        cap.setGravity(Gravity.CENTER);
        cap.setPadding(0, dp(8), 0, 0);
        hero.addView(cap);

        wrap.addView(hero);

        // Surface band (#151515): wells + active rows
        LinearLayout surface = new LinearLayout(this);
        surface.setOrientation(LinearLayout.VERTICAL);
        surface.setBackgroundColor(C_SURFACE);
        surface.setPadding(dp(20), dp(18), dp(20), dp(18));

        LinearLayout wellRow = new LinearLayout(this);
        wellRow.setOrientation(LinearLayout.HORIZONTAL);
        LinearLayout.LayoutParams wrLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        wrLp.bottomMargin = dp(18);
        wellRow.setLayoutParams(wrLp);
        addWell(wellRow, "Firmware", "MC801 2.9", true);
        addWell(wellRow, "State", "Armed", false);
        surface.addView(wellRow);

        addSpecRow(surface, "6K Open Gate", "Active \u00B7 MOV menu", C_NEEDLE, C_LIGHT);
        addSpecRow(surface, "5.9K Full", "Active \u00B7 MOV menu", C_NEEDLE, C_LIGHT);
        addSpecRow(surface, "Recording limit", "Unlimited", C_NEEDLE, C_LIGHT);

        wrap.addView(surface);

        // Calm confirmation + Restore stock
        LinearLayout bottom = new LinearLayout(this);
        bottom.setOrientation(LinearLayout.VERTICAL);
        bottom.setPadding(dp(20), dp(24), dp(20), dp(16));

        armedHeadline = new TextView(this);
        armedHeadline.setText("Safe to unplug USB-C");
        armedHeadline.setTextColor(C_NEEDLE);
        armedHeadline.setTextSize(15);
        armedHeadline.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        armedHeadline.setGravity(Gravity.CENTER);
        bottom.addView(armedHeadline);

        TextView sub = new TextView(this);
        sub.setText("Rec Quality (MOV) \u2192 scroll to bottom");
        sub.setTextColor(C_DIM);
        sub.setTextSize(11);
        sub.setGravity(Gravity.CENTER);
        sub.setPadding(0, dp(4), 0, dp(20));
        bottom.addView(sub);

        btnRestore = makeButton("Restore stock", C_HOVER, C_LIGHT, 13, 13);
        btnRestore.setOnClickListener(v -> applyAllAsync(false));
        bottom.addView(btnRestore);

        wrap.addView(bottom);
        return wrap;
    }

    private void addWell(LinearLayout parent, String label, String val, boolean addRightMargin) {
        LinearLayout well = new LinearLayout(this);
        well.setOrientation(LinearLayout.HORIZONTAL);
        well.setGravity(Gravity.CENTER_VERTICAL);
        well.setBackground(box(C_GROUND, 0, 4));
        well.setPadding(dp(10), dp(8), dp(10), dp(8));
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f);
        if (addRightMargin) lp.rightMargin = dp(8);
        well.setLayoutParams(lp);

        TextView k = new TextView(this);
        k.setText(label);
        k.setTextColor(C_DIM);
        k.setTextSize(11);
        k.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f));
        well.addView(k);

        TextView v = new TextView(this);
        v.setText(val);
        v.setTextColor(C_NEEDLE);
        v.setTextSize(12);
        v.setTypeface(Typeface.MONOSPACE);
        well.addView(v);

        parent.addView(well);
    }

    private void addSpecRow(LinearLayout parent, String left, String right, int leftColor, int rightColor) {
        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setPadding(0, dp(7), 0, dp(7));

        TextView l = new TextView(this);
        l.setText(left);
        l.setTextColor(leftColor);
        l.setTextSize(13);
        l.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1.0f));
        row.addView(l);

        TextView r = new TextView(this);
        r.setText(right);
        r.setTextColor(rightColor);
        r.setTextSize(11);
        r.setTypeface(Typeface.MONOSPACE);
        row.addView(r);

        parent.addView(row);
    }

    private Button makeButton(String label, int fill, int textColor, int textSp, int padV) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setStateListAnimator(null);
        b.setTextColor(textColor);
        b.setTextSize(textSp);
        b.setTypeface(Typeface.create("sans-serif-medium", Typeface.NORMAL));
        b.setBackground(box(fill, 0, 8));
        b.setPadding(dp(16), dp(padV), dp(16), dp(padV));
        b.setLayoutParams(new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT));
        return b;
    }

    private void toggleLog() {
        logExpanded = !logExpanded;
        logScroll.setVisibility(logExpanded ? View.VISIBLE : View.GONE);
        logBarToggle.setText(logExpanded ? "Hide \u25B4" : "Show \u25BE");
        if (logExpanded) {
            logScroll.post(() -> logScroll.fullScroll(View.FOCUS_DOWN));
        }
    }

    private void showHeaderStatus(String text, int dotColor, int textColor) {
        runOnUiThread(() -> {
            statusLabel.setText(text);
            statusLabel.setTextColor(textColor);
            statusDot.setBackground(box(dotColor, 0, 4));
        });
    }

    private void setUiState(UiState next, String headerText) {
        uiState = next;
        runOnUiThread(() -> {
            applyUiState();
            if (next == UiState.ARMED) {
                showHeaderStatus(headerText, C_SIGNAL, C_NEEDLE);
                logBarTitle.setText("Session log \u00B7 19/19 verified");
            } else if (next == UiState.READY) {
                showHeaderStatus(headerText, C_LIGHT, C_LIGHT);
                logBarTitle.setText("Session log");
            } else {
                showHeaderStatus(headerText, C_EDGE, C_DIM);
            }
        });
    }

    private void applyUiState() {
        viewWaiting.setVisibility(uiState == UiState.WAITING ? View.VISIBLE : View.GONE);
        viewReady.setVisibility(uiState == UiState.READY ? View.VISIBLE : View.GONE);
        viewArmed.setVisibility(uiState == UiState.ARMED ? View.VISIBLE : View.GONE);
        logBar.setVisibility(uiState == UiState.WAITING ? View.GONE : View.VISIBLE);

        boolean connected = (conn != null && epOut != null && epIn != null);
        btnConnect.setEnabled(!busy);
        btnConnect.setAlpha(busy ? 0.4f : 1.0f);

        btnUnlock.setEnabled(connected && !busy);
        btnUnlock.setAlpha((connected && !busy) ? 1.0f : 0.45f);
        btnUnlock.setText(busy ? "Unlocking\u2026" : "Unlock camera");

        btnRestore.setVisibility(connected ? View.VISIBLE : View.GONE);
        btnRestore.setEnabled(connected && !busy);
        btnRestore.setAlpha((connected && !busy) ? 1.0f : 0.45f);
        btnRestore.setText(busy ? "Restoring\u2026" : "Restore stock");
    }

    private void appendLog(String line) {
        runOnUiThread(() -> {
            logView.append("\n" + line);
            if (logExpanded) {
                logScroll.post(() -> logScroll.fullScroll(View.FOCUS_DOWN));
            }
        });
    }

    private UsbDevice findS5() {
        HashMap<String, UsbDevice> map = usbManager.getDeviceList();
        for (UsbDevice d : map.values()) {
            if (d.getVendorId() == VID && d.getProductId() == PID) return d;
        }
        return null;
    }

    private void connectDevice(UsbDevice dev) {
        if (usbManager.hasPermission(dev)) {
            openAndVerifyAsync(dev);
        } else {
            appendLog("requesting usb permission (04DA:2370)");
            showHeaderStatus("Allow USB", C_LIGHT, C_LIGHT);
            Intent permIntent = new Intent(ACTION_USB_PERMISSION);
            permIntent.setPackage(getPackageName());
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= 31) {
                flags |= PendingIntent.FLAG_MUTABLE;
            }
            PendingIntent pi = PendingIntent.getBroadcast(this, 0, permIntent, flags);
            usbManager.requestPermission(dev, pi);
        }
    }

    private synchronized void closeUsb() {
        if (conn != null) {
            if (usbIf != null) {
                try { conn.releaseInterface(usbIf); } catch (Exception ignored) {}
            }
            try { conn.close(); } catch (Exception ignored) {}
        }
        conn = null;
        usbIf = null;
        epOut = null;
        epIn = null;
        currentDevice = null;
    }

    private void openAndVerifyAsync(UsbDevice dev) {
        if (busy) return;
        busy = true;
        runOnUiThread(this::applyUiState);
        showHeaderStatus("Verifying", C_LIGHT, C_DIM);

        new Thread(() -> {
            try {
                closeUsb();
                if (dev.getInterfaceCount() < 1) throw new Exception("no usb interfaces");
                UsbInterface intf = dev.getInterface(0);
                UsbEndpoint out = null, in = null;
                for (int i = 0; i < intf.getEndpointCount(); i++) {
                    UsbEndpoint ep = intf.getEndpoint(i);
                    if (ep.getType() == UsbConstants.USB_ENDPOINT_XFER_BULK) {
                        if (ep.getDirection() == UsbConstants.USB_DIR_OUT) out = ep;
                        if (ep.getDirection() == UsbConstants.USB_DIR_IN) in = ep;
                    }
                }
                if (out == null || in == null) throw new Exception("bulk endpoints missing");
                UsbDeviceConnection c = usbManager.openDevice(dev);
                if (c == null) throw new Exception("openDevice returned null");
                if (!c.claimInterface(intf, true)) {
                    c.close();
                    throw new Exception("claimInterface(0) failed");
                }
                currentDevice = dev;
                usbIf = intf;
                epOut = out;
                epIn = in;
                conn = c;

                appendLog("connected: DC-S5 (04DA:2370)");
                verifySignatures();
                int capWord = readHalf(0x868261B6);
                isUnlocked = (capWord == 0x2000);
                busy = false;
                if (isUnlocked) {
                    runOnUiThread(() -> armedHeadline.setText("Safe to unplug USB-C"));
                    setUiState(UiState.ARMED, "Armed");
                } else {
                    setUiState(UiState.READY, "Ready");
                }
            } catch (Exception e) {
                closeUsb();
                busy = false;
                appendLog("error: " + e.getMessage());
                runOnUiThread(() -> {
                    waitingHint.setText("Error: " + e.getMessage());
                    setUiState(UiState.WAITING, "Failed");
                });
            }
        }).start();
    }

    private void applyAllAsync(boolean unlock) {
        if (busy || conn == null) return;
        busy = true;
        runOnUiThread(this::applyUiState);
        showHeaderStatus(unlock ? "Writing" : "Restoring", C_LIGHT, C_DIM);

        new Thread(() -> {
            try {
                verifySignatures();
                for (int[] p : PATCHES) {
                    int addr = p[0];
                    int target = unlock ? p[1] : p[2];
                    writeHalf(addr, target);
                    int rb = readHalf(addr);
                    if (rb != target) {
                        throw new Exception(String.format(Locale.US,
                                "verify mismatch 0x%08X: got 0x%04X want 0x%04X", addr, rb, target));
                    }
                }
                isUnlocked = unlock;
                busy = false;
                if (unlock) {
                    appendLog("ok: 19/19 words verified (6K + 5.9K + unlimited + suspend-safe)");
                    runOnUiThread(() -> armedHeadline.setText("Safe to unplug USB-C"));
                    setUiState(UiState.ARMED, "Armed");
                } else {
                    appendLog("ok: 19/19 words restored to stock");
                    setUiState(UiState.READY, "Ready");
                }
            } catch (Exception e) {
                busy = false;
                appendLog("error: " + e.getMessage());
                runOnUiThread(() -> {
                    readySubNote.setText("Error: " + e.getMessage());
                    applyUiState();
                    showHeaderStatus("Error", C_SIGNAL, C_NEEDLE);
                });
            }
        }).start();
    }

    private static int frameSum(byte[] buf, int len) {
        int s = 0;
        for (int i = 1; i + 2 < len; i++) {
            s = (s + (buf[i] & 0xFF)) & 0xFF;
        }
        return s;
    }

    private void prepare(int index) throws Exception {
        int r = conn.controlTransfer(0x40, 0, 0, index, null, 0, TIMEOUT_MS);
        if (r < 0) throw new Exception("prepare(" + index + ") failed: " + r);
    }

    private int readHalf(int addr) throws Exception {
        byte[] tx = new byte[16];
        tx[0] = 8;
        tx[2] = (byte) 0xFF;
        tx[3] = (byte) 0x9B;
        tx[4] = (byte) (addr & 0xFF);
        tx[5] = (byte) ((addr >>> 8) & 0xFF);
        tx[6] = (byte) ((addr >>> 16) & 0xFF);
        tx[7] = (byte) ((addr >>> 24) & 0xFF);
        tx[14] = (byte) frameSum(tx, 16);

        prepare(0);
        int w = conn.bulkTransfer(epOut, tx, 16, TIMEOUT_MS);
        if (w != 16) throw new Exception("read bulk out failed: " + w);

        byte[] tb = new byte[64];
        prepare(1);
        int n1 = conn.bulkTransfer(epIn, tb, 64, TIMEOUT_MS);
        if (n1 != 1 || (tb[0] & 0xFF) != 8) throw new Exception("bad read type len=" + n1);

        byte[] rx = new byte[64];
        prepare(1);
        int n2 = conn.bulkTransfer(epIn, rx, 64, TIMEOUT_MS);
        if (n2 != 16) throw new Exception("bad read reply len=" + n2);
        if ((rx[3] & 0xFF) != 0x36 || (rx[14] & 0xFF) != frameSum(rx, 16) || rx[15] != 0) {
            throw new Exception("bad read checksum/opcode");
        }
        return (rx[4] & 0xFF) | ((rx[5] & 0xFF) << 8);
    }

    private void writeHalf(int addr, int val) throws Exception {
        byte[] tx = new byte[16];
        tx[0] = 8;
        tx[2] = (byte) 0xFF;
        tx[3] = (byte) 0x9C;
        tx[4] = (byte) (addr & 0xFF);
        tx[5] = (byte) ((addr >>> 8) & 0xFF);
        tx[6] = (byte) ((addr >>> 16) & 0xFF);
        tx[7] = (byte) ((addr >>> 24) & 0xFF);
        tx[8] = (byte) (val & 0xFF);
        tx[9] = (byte) ((val >>> 8) & 0xFF);
        tx[14] = (byte) frameSum(tx, 16);

        prepare(0);
        int w = conn.bulkTransfer(epOut, tx, 16, TIMEOUT_MS);
        if (w != 16) throw new Exception("write bulk out failed: " + w);

        byte[] tb = new byte[64];
        prepare(1);
        int n1 = conn.bulkTransfer(epIn, tb, 64, TIMEOUT_MS);
        if (n1 != 1) throw new Exception("bad write ack type len=" + n1);
        int t = tb[0] & 0xFF;
        if (t != 8 && t != 1) throw new Exception("bad write ack type=" + t);

        byte[] rx = new byte[64];
        prepare(1);
        int n2 = conn.bulkTransfer(epIn, rx, 64, TIMEOUT_MS);
        if (n2 < 6) throw new Exception("short write ack len=" + n2);
        int op = rx[3] & 0xFF;
        if ((rx[0] & 0xFF) != 8 || rx[1] != 0 || (rx[2] & 0xFF) != 0xFF
                || (rx[n2 - 2] & 0xFF) != frameSum(rx, n2) || rx[n2 - 1] != 0
                || (op != 0x00 && op != 0x01)) {
            throw new Exception("write nack or bad checksum");
        }
    }

    private void verifySignatures() throws Exception {
        for (int[] s : SIG_CHECKS) {
            int addr = s[0];
            int v = readHalf(addr);
            if (v != s[1] && (s[2] == -1 || v != s[2])) {
                throw new Exception(String.format(Locale.US,
                        "signature mismatch 0x%08X (got 0x%04X)", addr, v));
            }
        }
        appendLog("signatures verified (MC801 2.9 \u00B7 13 anchors)");
    }
}
