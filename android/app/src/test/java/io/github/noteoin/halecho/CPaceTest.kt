/* CPace against draft-irtf-cfrg-cpace-21 appendix B.3, as tests/test_cpace.py checks the PC. */
package io.github.noteoin.halecho

import com.goterl.lazysodium.LazySodiumJava
import com.goterl.lazysodium.SodiumJava
import io.github.noteoin.halecho.crypto.CPace
import io.github.noteoin.halecho.crypto.PairingFailed
import io.github.noteoin.halecho.crypto.Pairing
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Test

class CPaceTest {
    private val sodium = LazySodiumJava(SodiumJava())
    private fun hex(s: String) = Pairing.unhex(s)!!

    private val prs = "Password".toByteArray()
    private val ci = hex("0b415f696e69746961746f720b425f726573706f6e646572")
    private val sid = hex("7e4b4791d6a8ef019b936c79fb7f2c57")

    @Test
    fun lvCatMatchesTheDraft() {
        assertEquals("043132333401350003363738", Pairing.hex(CPace.lvCat("1234".toByteArray(), "5".toByteArray(), ByteArray(0), "678".toByteArray())))
    }

    @Test
    fun generatorMatchesTheDraft() {
        assertEquals(
            "222b6b195fe84b1652badb6f6a3ae3d24341e7306967f0b8115b40d5698c7e56",
            Pairing.hex(CPace.generator(sodium, prs, ci, sid)),
        )
    }

    @Test
    fun messagesAndKeyMatchTheDraft() {
        val a = CPace(sodium, prs, ci, sid, "ADa".toByteArray(), hex("da3d23700a9e5699258aef94dc060dfda5ebb61f02a5ea77fad53f4ff0976d08"))
        val b = CPace(sodium, prs, ci, sid, "ADb".toByteArray(), hex("d2316b454718c35362d83d69df6320f38578ed5984651435e2949762d900b80d"))
        assertEquals("d6bac480f2c386c394efc7c47adb9925dcd2630b64f240c50f8d0eec482b9157", Pairing.hex(a.message))
        assertEquals("3ea7e0b19560d7c0b0f5734f63b955286dfa8232b5ebe63324e2d9e7433f7258", Pairing.hex(b.message))
        val isk = "b69effbf61b51d56401c0f65601abe428de8206feaaf0e32198896dcae7b35cd" +
            "2b38950a39dfd5d4a79164614c2984f7daa460b588c1e80c3fa2068af7900447"
        assertEquals(isk, Pairing.hex(a.finish(b.message, "ADb".toByteArray(), initiator = true).isk))
        assertEquals(isk, Pairing.hex(b.finish(a.message, "ADa".toByteArray(), initiator = false).isk))
    }

    @Test
    fun matchingCodesConfirm() {
        val a = CPace(sodium, "123456".toByteArray(), Pairing.CI, sid, "device".toByteArray())
        val b = CPace(sodium, "123456".toByteArray(), Pairing.CI, sid, "pc".toByteArray())
        val ka = a.finish(b.message, "pc".toByteArray(), initiator = true)
        val kb = b.finish(a.message, "device".toByteArray(), initiator = false)
        ka.check(kb.ownTag)
        kb.check(ka.ownTag)
        assertArrayEquals(ka.isk, kb.isk)
    }

    @Test(expected = PairingFailed::class)
    fun wrongCodeFailsConfirmation() {
        val a = CPace(sodium, "123456".toByteArray(), Pairing.CI, sid, "device".toByteArray())
        val b = CPace(sodium, "654321".toByteArray(), Pairing.CI, sid, "pc".toByteArray())
        a.finish(b.message, "pc".toByteArray(), initiator = true).check(b.finish(a.message, "device".toByteArray(), initiator = false).ownTag)
    }

    @Test(expected = PairingFailed::class)
    fun identityPointIsRefused() {
        CPace(sodium, "123456".toByteArray(), Pairing.CI, sid, "device".toByteArray()).finish(ByteArray(32), "pc".toByteArray(), initiator = true)
    }
}
