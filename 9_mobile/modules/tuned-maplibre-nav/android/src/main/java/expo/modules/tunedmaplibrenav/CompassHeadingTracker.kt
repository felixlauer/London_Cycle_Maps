package expo.modules.tunedmaplibrenav

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlin.math.roundToInt

/**
 * Phone compass heading for nav puck / camera.
 * First rotation reading → [hasReliableHeading]; cleared on [stop].
 */
class CompassHeadingTracker(
  context: Context,
  private val onAvailabilityChanged: (hasHeading: Boolean) -> Unit,
) : SensorEventListener {

  private val sensorManager =
    context.applicationContext.getSystemService(Context.SENSOR_SERVICE) as SensorManager
  private val rotationSensor: Sensor? =
    sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
      ?: sensorManager.getDefaultSensor(Sensor.TYPE_ORIENTATION)

  @Volatile
  var headingDegrees: Float? = null
    private set

  @Volatile
  var hasReliableHeading: Boolean = false
    private set

  private var listening: Boolean = false

  fun start() {
    if (listening) return
    val sensor = rotationSensor ?: run {
      setReliable(false)
      return
    }
    listening = true
    sensorManager.registerListener(this, sensor, SensorManager.SENSOR_DELAY_UI)
  }

  fun stop() {
    if (!listening) return
    listening = false
    sensorManager.unregisterListener(this)
    headingDegrees = null
    setReliable(false)
  }

  override fun onSensorChanged(event: SensorEvent?) {
    if (event == null) return
    val deg = when (event.sensor.type) {
      Sensor.TYPE_ROTATION_VECTOR -> {
        val rotation = FloatArray(9)
        SensorManager.getRotationMatrixFromVector(rotation, event.values)
        val orientation = FloatArray(3)
        SensorManager.getOrientation(rotation, orientation)
        normalizeDegrees(Math.toDegrees(orientation[0].toDouble()).toFloat())
      }
      Sensor.TYPE_ORIENTATION -> normalizeDegrees(event.values[0])
      else -> return
    }
    headingDegrees = deg
    setReliable(true)
  }

  override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
    // Intentionally ignore — many devices stay SENSOR_STATUS_UNRELIABLE while
    // still delivering usable rotation vectors; gating on accuracy forced the circle.
  }

  private fun setReliable(value: Boolean) {
    if (hasReliableHeading == value) return
    hasReliableHeading = value
    if (!value) headingDegrees = null
    onAvailabilityChanged(value)
  }

  private fun normalizeDegrees(raw: Float): Float {
    var d = raw % 360f
    if (d < 0f) d += 360f
    return (d * 10f).roundToInt() / 10f
  }
}
