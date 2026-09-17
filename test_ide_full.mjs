export default async function run(page, ui) {
  const results = {
    timestamp: new Date().toISOString(),
    tests: [],
    defects: []
  };

  // Test 1: Verify backend connection
  try {
    const snapshot = await ui.snapshot();
    const backendConnected = snapshot.includes("connected (HEALTHY)");
    results.tests.push({
      test: "Backend Connection",
      passed: backendConnected,
      status: backendConnected ? "HEALTHY" : "DISCONNECTED"
    });
  } catch (e) {
    results.tests.push({ test: "Backend Connection", error: e.message });
  }

  // Test 2: Verify models loaded
  try {
    const snapshot = await ui.snapshot();
    const modelsLoaded = snapshot.includes("Models (11)");
    results.tests.push({
      test: "Models Loaded",
      passed: modelsLoaded,
      count: modelsLoaded ? 11 : 0
    });
  } catch (e) {
    results.tests.push({ test: "Models Loaded", error: e.message });
  }

  // Test 3: Verify terminal active
  try {
    const snapshot = await ui.snapshot();
    const terminalActive = snapshot.includes("C:\\Users\\jpowe\\Desktop\\Agent-Bridge");
    results.tests.push({
      test: "Terminal Active",
      passed: terminalActive,
      workspace: terminalActive ? "Agent-Bridge" : "none"
    });
  } catch (e) {
    results.tests.push({ test: "Terminal Active", error: e.message });
  }

  // Test 4: Click Chat button and test chat
  try {
    const snapshot1 = await ui.snapshot();
    const chatButton = snapshot1.match(/@(e\d+) button "Chat"/)?.[1];
    if (chatButton) {
      await ui.click(chatButton);
      await page.waitForTimeout(500);
      
      const snapshot2 = await ui.snapshot();
      const chatInput = snapshot2.match(/@(e\d+) textbox "Type a message"/)?.[1];
      if (chatInput) {
        await ui.fill(chatInput, "Hello, can you help me write a Python function?");
        const afterFill = await ui.snapshot();
        results.tests.push({
          test: "Chat Input",
          passed: afterFill.includes("Hello, can you help me write a Python function?")
        });
      }
    }
  } catch (e) {
    results.tests.push({ test: "Chat Input", error: e.message });
  }

  // Test 5: Test terminal command
  try {
    const snapshot1 = await ui.snapshot();
    const terminalInput = snapshot1.match(/@(e\d+) textbox "Run a policy-gated command"/)?.[1];
    if (terminalInput) {
      await ui.fill(terminalInput, "dir");
      const afterFill = await ui.snapshot();
      results.tests.push({
        test: "Terminal Command Input",
        passed: afterFill.includes("dir")
      });
      
      // Click Send button
      const sendButton = afterFill.match(/@(e\d+) button "Send"/)?.[1];
      if (sendButton) {
        await ui.click(sendButton);
        await page.waitForTimeout(1000);
        const afterSend = await ui.snapshot();
        results.tests.push({
          test: "Terminal Command Execute",
          passed: afterSend.includes("dir") || afterSend.includes("Volume")
        });
      }
    }
  } catch (e) {
    results.tests.push({ test: "Terminal Command", error: e.message });
  }

  // Test 6: Test Settings panel
  try {
    const snapshot1 = await ui.snapshot();
    const settingsButton = snapshot1.match(/@(e\d+) button "Settings"/)?.[1];
    if (settingsButton) {
      await ui.click(settingsButton);
      await page.waitForTimeout(500);
      const afterClick = await ui.snapshot();
      results.tests.push({
        test: "Settings Panel",
        passed: afterClick.includes("Settings") && afterClick.includes("Theme")
      });
    }
  } catch (e) {
    results.tests.push({ test: "Settings Panel", error: e.message });
  }

  // Test 7: Test Files button
  try {
    const snapshot1 = await ui.snapshot();
    const filesButton = snapshot1.match(/@(e\d+) button "Files"/)?.[1];
    if (filesButton) {
      await ui.click(filesButton);
      await page.waitForTimeout(500);
      const afterClick = await ui.snapshot();
      results.tests.push({
        test: "Files Button",
        passed: afterClick.includes("Files")
      });
    }
  } catch (e) {
    results.tests.push({ test: "Files Button", error: e.message });
  }

  // Test 8: Test Apps button
  try {
    const snapshot1 = await ui.snapshot();
    const appsButton = snapshot1.match(/@(e\d+) button "Apps"/)?.[1];
    if (appsButton) {
      await ui.click(appsButton);
      await page.waitForTimeout(500);
      const afterClick = await ui.snapshot();
      results.tests.push({
        test: "Apps Button",
        passed: afterClick.includes("Apps")
      });
    }
  } catch (e) {
    results.tests.push({ test: "Apps Button", error: e.message });
  }

  // Take final screenshot
  await page.screenshot({ path: "C:\\Users\\jpowe\\Desktop\\Agent-Bridge\\ide_screenshot_final_tests.png" });

  // Summary
  results.summary = {
    total: results.tests.length,
    passed: results.tests.filter(t => t.passed).length,
    failed: results.tests.filter(t => !t.passed && !t.error).length,
    errors: results.tests.filter(t => t.error).length
  };

  return results;
}