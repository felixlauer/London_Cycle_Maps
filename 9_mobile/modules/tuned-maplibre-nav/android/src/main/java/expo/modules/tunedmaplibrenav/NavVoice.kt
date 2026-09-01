package expo.modules.tunedmaplibrenav

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Build
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import android.util.Log
import java.util.Locale

/**
 * Speaks MapLibre voice-instruction milestones.
 * Ducks other audio for the length of the announcement (music keeps playing, quieter).
 *
 * The device default engine and locale alone give the flat, robotic embedded voice.
 * The Google engine is requested explicitly and its best en-GB voice picked by hand,
 * because Android otherwise sticks with whatever low-quality voice is installed.
 */
class NavVoice(context: Context) {

  private val appContext = context.applicationContext
  private val audioManager =
    appContext.getSystemService(Context.AUDIO_SERVICE) as? AudioManager

  private var tts: TextToSpeech? = null
  private var ready = false
  private var pendingText: String? = null
  private var focusRequest: AudioFocusRequest? = null
  private var triedFallbackEngine = false

  var muted: Boolean = false
    set(value) {
      field = value
      if (value) stopSpeaking()
    }

  init {
    createEngine(GOOGLE_TTS_PACKAGE)
  }

  private fun createEngine(enginePackage: String?) {
    tts = TextToSpeech(appContext, { status -> onInit(status, enginePackage) }, enginePackage)
  }

  private fun onInit(status: Int, enginePackage: String?) {
    if (status != TextToSpeech.SUCCESS) {
      // Google TTS is absent or disabled — fall back to whatever the device ships.
      if (enginePackage != null && !triedFallbackEngine) {
        triedFallbackEngine = true
        Log.w(TAG, "$enginePackage unavailable, using the default engine")
        try {
          tts?.shutdown()
        } catch (_: Exception) {
          // ignore
        }
        createEngine(null)
        return
      }
      ready = false
      Log.w(TAG, "TextToSpeech unavailable (status=$status)")
      return
    }

    ready = true
    val engine = tts ?: return
    engine.language = Locale.UK
    selectVoice(engine)
    engine.setSpeechRate(SPEECH_RATE)
    engine.setPitch(SPEECH_PITCH)
    engine.setOnUtteranceProgressListener(object : android.speech.tts.UtteranceProgressListener() {
      override fun onStart(utteranceId: String?) = Unit
      override fun onDone(utteranceId: String?) = abandonFocus()
      @Deprecated("Deprecated in Java")
      override fun onError(utteranceId: String?) = abandonFocus()
    })
    pendingText?.let { text ->
      pendingText = null
      speak(text)
    }
  }

  /**
   * Pick the most natural en-GB voice available.
   *
   * Setting only the locale leaves Android on whatever voice happens to be default,
   * which is usually the flat embedded one. Voices are ranked by reported quality —
   * Google's `en-gb-x-*-network` voices sit at the top and are the ones that sound
   * human. Ties go to a voice that works without a connection, because a network
   * voice that cannot be reached mid-ride fails silently, and then to lower latency.
   */
  private fun selectVoice(engine: TextToSpeech) {
    val candidates = try {
      engine.voices?.filterNotNull().orEmpty()
    } catch (e: Exception) {
      Log.w(TAG, "voices unavailable: ${e.message}")
      return
    }
    val chosen = candidates
      .filter { it.locale.language == "en" && it.locale.country == "GB" }
      .filterNot { it.features?.contains(TextToSpeech.Engine.KEY_FEATURE_NOT_INSTALLED) == true }
      .maxWithOrNull(
        compareBy<Voice> { it.quality }
          .thenBy { if (it.isNetworkConnectionRequired) 0 else 1 }
          .thenBy { -it.latency },
      ) ?: return
    try {
      engine.voice = chosen
      Log.i(
        TAG,
        "voice=${chosen.name} quality=${chosen.quality} network=${chosen.isNetworkConnectionRequired}",
      )
    } catch (e: Exception) {
      Log.w(TAG, "setVoice failed: ${e.message}")
    }
  }

  /**
   * @param flush replace anything currently speaking (maneuver cues, a stale
   *   "Rerouting"). Pass false to queue after the current utterance so
   *   "Rerouting" can be followed immediately by the new next-turn.
   */
  fun speak(text: String?, flush: Boolean = true) {
    val clean = text?.trim().orEmpty()
    if (clean.isEmpty() || muted) return
    if (!ready) {
      pendingText = clean
      return
    }
    requestFocus()
    val mode = if (flush) TextToSpeech.QUEUE_FLUSH else TextToSpeech.QUEUE_ADD
    tts?.speak(clean, mode, null, "tuned-nav-${clean.hashCode()}-${System.nanoTime()}")
  }

  fun stopSpeaking() {
    try {
      tts?.stop()
    } catch (_: Exception) {
      // ignore
    }
    abandonFocus()
  }

  fun release() {
    stopSpeaking()
    try {
      tts?.shutdown()
    } catch (_: Exception) {
      // ignore
    }
    tts = null
    ready = false
  }

  private fun requestFocus() {
    val manager = audioManager ?: return
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        val attributes = AudioAttributes.Builder()
          .setUsage(AudioAttributes.USAGE_ASSISTANCE_NAVIGATION_GUIDANCE)
          .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
          .build()
        val request = AudioFocusRequest
          .Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK)
          .setAudioAttributes(attributes)
          .build()
        focusRequest = request
        manager.requestAudioFocus(request)
      } else {
        @Suppress("DEPRECATION")
        manager.requestAudioFocus(
          null,
          AudioManager.STREAM_MUSIC,
          AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_MAY_DUCK,
        )
      }
    } catch (e: Exception) {
      Log.w(TAG, "requestAudioFocus failed: ${e.message}")
    }
  }

  private fun abandonFocus() {
    val manager = audioManager ?: return
    try {
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        focusRequest?.let { manager.abandonAudioFocusRequest(it) }
        focusRequest = null
      } else {
        @Suppress("DEPRECATION")
        manager.abandonAudioFocus(null)
      }
    } catch (_: Exception) {
      // ignore
    }
  }

  companion object {
    private const val TAG = "TunedNavVoice"
    private const val GOOGLE_TTS_PACKAGE = "com.google.android.tts"
    private const val SPEECH_RATE = 1.0f
    private const val SPEECH_PITCH = 1.0f
  }
}
