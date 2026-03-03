package com.yumi.mobile

import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.TextView
import android.widget.EditText
import android.widget.ProgressBar
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.swiperefreshlayout.widget.SwipeRefreshLayout
import com.google.android.material.button.MaterialButton
import com.google.android.material.button.MaterialButtonToggleGroup

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private lateinit var urlInput: EditText
    private lateinit var connectButton: MaterialButton
    private lateinit var openExternalButton: MaterialButton
    private lateinit var statusText: TextView
    private lateinit var navToggle: MaterialButtonToggleGroup
    private lateinit var progressBar: ProgressBar
    private lateinit var swipeRefresh: SwipeRefreshLayout

    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    private var currentBaseUrl: String = DEFAULT_URL
    private var currentView: String = "dashboard"

    private val fileChooserLauncher =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val uris = WebChromeClient.FileChooserParams.parseResult(result.resultCode, result.data)
            filePathCallback?.onReceiveValue(uris)
            filePathCallback = null
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        webView = findViewById(R.id.webView)
        urlInput = findViewById(R.id.urlInput)
        connectButton = findViewById(R.id.connectButton)
        openExternalButton = findViewById(R.id.openExternalButton)
        statusText = findViewById(R.id.statusText)
        navToggle = findViewById(R.id.navToggle)
        progressBar = findViewById(R.id.progressBar)
        swipeRefresh = findViewById(R.id.swipeRefresh)

        setupWebView()
        setupNavigation()
        setupBackBehavior()

        val prefs = getSharedPreferences("yumi_mobile", Context.MODE_PRIVATE)
        val savedUrl = normalizeUrl(prefs.getString("server_url", DEFAULT_URL) ?: DEFAULT_URL)
        currentBaseUrl = savedUrl
        urlInput.setText(savedUrl)

        connectButton.setOnClickListener {
            val value = normalizeUrl(urlInput.text.toString())
            urlInput.setText(value)
            prefs.edit().putString("server_url", value).apply()
            currentBaseUrl = value
            loadCurrentView()
        }

        openExternalButton.setOnClickListener {
            val target = buildTargetUrl(currentBaseUrl, currentView)
            openInBrowser(target)
        }

        swipeRefresh.setOnRefreshListener {
            webView.reload()
        }

        navToggle.check(R.id.navDashboard)
    }

    private fun setupWebView() {
        val settings: WebSettings = webView.settings
        settings.javaScriptEnabled = true
        settings.domStorageEnabled = true
        settings.allowFileAccess = true
        settings.loadsImagesAutomatically = true
        settings.mediaPlaybackRequiresUserGesture = false
        settings.mixedContentMode = WebSettings.MIXED_CONTENT_ALWAYS_ALLOW

        webView.webViewClient = object : WebViewClient() {
            override fun onPageStarted(view: WebView?, url: String?, favicon: android.graphics.Bitmap?) {
                val loadingUrl = url ?: buildTargetUrl(currentBaseUrl, currentView)
                statusText.text = getString(R.string.status_loading, loadingUrl)
                super.onPageStarted(view, url, favicon)
            }

            override fun onPageFinished(view: WebView?, url: String?) {
                swipeRefresh.isRefreshing = false
                statusText.text = getString(R.string.status_connected, url ?: buildTargetUrl(currentBaseUrl, currentView))
                super.onPageFinished(view, url)
            }

            override fun onReceivedError(
                view: WebView?,
                request: WebResourceRequest?,
                error: WebResourceError?,
            ) {
                if (request?.isForMainFrame == true) {
                    swipeRefresh.isRefreshing = false
                    statusText.setText(R.string.status_failed)
                }
                super.onReceivedError(view, request, error)
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onProgressChanged(view: WebView?, newProgress: Int) {
                progressBar.progress = newProgress
                progressBar.visibility = if (newProgress in 1..99) View.VISIBLE else View.GONE
                super.onProgressChanged(view, newProgress)
            }

            override fun onShowFileChooser(
                webView: WebView?,
                filePathCallback: ValueCallback<Array<Uri>>?,
                fileChooserParams: FileChooserParams?,
            ): Boolean {
                this@MainActivity.filePathCallback?.onReceiveValue(null)
                this@MainActivity.filePathCallback = filePathCallback

                return try {
                    val intent: Intent = fileChooserParams?.createIntent() ?: Intent(Intent.ACTION_GET_CONTENT).apply {
                        type = "*/*"
                    }
                    fileChooserLauncher.launch(intent)
                    true
                } catch (_: Exception) {
                    this@MainActivity.filePathCallback = null
                    false
                }
            }
        }
    }

    private fun setupNavigation() {
        navToggle.addOnButtonCheckedListener { _, checkedId, isChecked ->
            if (!isChecked) return@addOnButtonCheckedListener
            currentView =
                when (checkedId) {
                    R.id.navDashboard -> "dashboard"
                    R.id.navPlanner -> "planner"
                    R.id.navNotes -> "notes"
                    R.id.navQa -> "qa"
                    R.id.navMaterials -> "materials"
                    R.id.navAudio -> "audio"
                    else -> "dashboard"
                }
            loadCurrentView()
        }
    }

    private fun setupBackBehavior() {
        onBackPressedDispatcher.addCallback(
            this,
            object : OnBackPressedCallback(true) {
                override fun handleOnBackPressed() {
                    if (webView.canGoBack()) {
                        webView.goBack()
                    } else {
                        finish()
                    }
                }
            },
        )
    }

    private fun normalizeUrl(raw: String): String {
        val trim = raw.trim()
        if (trim.isEmpty()) return DEFAULT_URL
        if (trim.startsWith("http://") || trim.startsWith("https://")) return trim
        return "http://$trim"
    }

    private fun buildTargetUrl(baseUrl: String, view: String): String {
        val normalized = normalizeUrl(baseUrl)
        val uri = Uri.parse(normalized)
        val builder = uri.buildUpon().clearQuery()
        builder.appendQueryParameter("view", view)
        builder.appendQueryParameter("mobile", "1")
        return builder.build().toString()
    }

    private fun loadCurrentView() {
        val target = buildTargetUrl(currentBaseUrl, currentView)
        loadUrl(target)
    }

    private fun loadUrl(url: String) {
        statusText.text = getString(R.string.status_loading, url)
        webView.loadUrl(url)
    }

    private fun openInBrowser(url: String) {
        try {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            startActivity(intent)
        } catch (_: ActivityNotFoundException) {
            statusText.setText(R.string.status_open_external_failed)
        }
    }

    companion object {
        private const val DEFAULT_URL = "http://192.168.1.100:8501"
    }
}
